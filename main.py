import asyncio
import logging
import os
import signal

from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

from config import (
    TOKEN,
    PORT,
    WEBHOOK_URL,
    WEBHOOK_SECRET,
    RENDER_EXTERNAL_URL,
    RENDER_EXTERNAL_HOSTNAME,
    is_admin,
    admin_only,
)
from modules.attendance import meeting_handler
from modules.daily_report import count_handler
from modules.qa import answer_question, ai_status
from modules.admin import add_member, remove_member, list_members

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_admin(user_id):
        text = (
            "Welcome to the Protocol Bot (Admin Mode)!\n\n"
            "Admin Commands:\n"
            "/meeting - Start meeting attendance & generate weekly roster\n"
            "/count - Record daily service counts and generate report\n"
            "/ai_status - Check AI availability and cooldown\n"
            "/add <name> - Add a member\n"
            "/remove <name> - Remove a member\n"
            "/list - List all members\n\n"
            "You can also ask general questions."
        )
    else:
        text = (
            "Welcome to the Protocol Bot!\n\n"
            "I'm here to answer your questions about Protocol roles, duties, and general inquiries.\n"
            "Just type your question below!"
        )
    await update.message.reply_text(text)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Handler error while processing update", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Sorry, something went wrong while handling your message. Please try again."
            )
        except Exception:
            pass


def build_application():
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_error_handler(on_error)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ai_status", ai_status))
    application.add_handler(meeting_handler)
    application.add_handler(count_handler)
    application.add_handler(CommandHandler("add", admin_only(add_member)))
    application.add_handler(CommandHandler("remove", admin_only(remove_member)))
    application.add_handler(CommandHandler("list", admin_only(list_members)))
    application.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), answer_question)
    )
    return application


def _resolve_public_url():
    if WEBHOOK_URL:
        return WEBHOOK_URL.rstrip("/")
    if RENDER_EXTERNAL_URL:
        return RENDER_EXTERNAL_URL.rstrip("/")
    if RENDER_EXTERNAL_HOSTNAME:
        return f"https://{RENDER_EXTERNAL_HOSTNAME}".rstrip("/")
    return ""


async def _handle_root(_request):
    return web.Response(
        text="Protocol Bot is online.\nUse Telegram to interact with this bot.",
        content_type="text/plain",
    )


async def _handle_healthz(request):
    application = request.app.get("ptb_app")
    payload = {"status": "ok", "service": "protocol-bot"}
    if application:
        try:
            info = await application.bot.get_webhook_info()
            payload["webhook_url"] = info.url
            payload["pending_updates"] = info.pending_update_count
            payload["last_error"] = info.last_error_message or None
        except Exception as exc:
            payload["webhook_check_error"] = str(exc)
    return web.json_response(payload)


async def _handle_telegram_webhook(request):
    application = request.app["ptb_app"]

    # Validate Telegram secret header when secret_token is configured
    expected_secret = request.app.get("webhook_secret")
    if expected_secret:
        received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if received != expected_secret:
            logger.warning("Webhook rejected: invalid secret token header")
            return web.Response(status=403, text="Forbidden")

    try:
        data = await request.json()
    except Exception:
        logger.exception("Invalid webhook JSON")
        return web.Response(status=400, text="Invalid JSON")

    update = Update.de_json(data, application.bot)
    if not update:
        return web.Response(status=200, text="ok")

    update_type = "message" if update.message else update.callback_query and "callback" or "other"
    logger.info("Incoming update id=%s type=%s", update.update_id, update_type)

    try:
        await application.process_update(update)
    except Exception:
        logger.exception("Failed to process update id=%s", update.update_id)
        return web.Response(status=500, text="Processing failed")

    return web.Response(status=200, text="ok")


async def _on_startup(app):
    application = app["ptb_app"]
    await application.initialize()
    await application.start()

    base_url = app["public_url"]
    webhook_path = app["webhook_path"]
    full_webhook_url = f"{base_url}{webhook_path}"

    await application.bot.set_webhook(
        url=full_webhook_url,
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=True,
    )
    info = await application.bot.get_webhook_info()
    logger.info("Telegram webhook registered: %s", info.url)
    if info.last_error_message:
        logger.warning("Webhook last error: %s", info.last_error_message)


async def _on_shutdown(app):
    application = app["ptb_app"]
    # Do NOT delete webhook on shutdown — Render restarts would break the bot.
    await application.stop()
    await application.shutdown()
    logger.info("Bot shutdown complete")


async def run_webhook_server():
    base_url = _resolve_public_url()
    if not base_url:
        raise RuntimeError(
            "Set WEBHOOK_URL=https://your-app.onrender.com on Render "
            "(or rely on RENDER_EXTERNAL_URL / RENDER_EXTERNAL_HOSTNAME)."
        )

    webhook_path = f"/webhook/{WEBHOOK_SECRET}"
    listen_port = int(os.getenv("PORT", str(PORT)))

    application = build_application()
    app = web.Application()
    app["ptb_app"] = application
    app["public_url"] = base_url
    app["webhook_path"] = webhook_path
    app["webhook_secret"] = WEBHOOK_SECRET

    app.router.add_get("/", _handle_root)
    app.router.add_get("/healthz", _handle_healthz)
    app.router.add_post(webhook_path, _handle_telegram_webhook)

    app.on_startup.append(_on_startup)
    app.on_shutdown.append(_on_shutdown)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=listen_port)
    await site.start()

    logger.info("HTTP server listening on 0.0.0.0:%s", listen_port)
    logger.info("Root: %s/", base_url)
    logger.info("Health: %s/healthz", base_url)
    logger.info("Webhook: %s%s", base_url, webhook_path)

    stop_event = asyncio.Event()

    def _stop(*_args):
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass

    await stop_event.wait()
    await runner.cleanup()


def run_polling():
    application = build_application()
    logger.info("Bot is running in POLLING mode...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    public_url = _resolve_public_url()
    if public_url:
        asyncio.run(run_webhook_server())
    else:
        run_polling()
