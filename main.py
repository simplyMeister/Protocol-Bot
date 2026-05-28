import logging
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from config import (
    TOKEN,
    PORT,
    WEBHOOK_URL,
    WEBHOOK_SECRET,
    RENDER_EXTERNAL_URL,
    is_admin,
    admin_only,
)
from modules.attendance import meeting_handler
from modules.daily_report import count_handler
from modules.qa import answer_question, ai_status
from modules.admin import add_member, remove_member, list_members

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_admin(user_id):
        await update.message.reply_text(
            "Welcome to the **Protocol Bot** (Admin Mode)!\n\n"
            "**Admin Commands:**\n"
            "/meeting - Start meeting attendance & generate weekly roster\n"
            "/count - Record daily service counts and generate report\n"
            "/ai_status - Check AI availability and cooldown\n"
            "/add <name> - Add a member\n"
            "/remove <name> - Remove a member\n"
            "/list - List all members\n\n"
            "You can also ask general questions.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "Welcome to the **Protocol Bot**!\n\n"
            "I'm here to answer your questions about Protocol roles, duties, and general inquiries.\n"
            "Just type your question below! 👇",
            parse_mode="Markdown"
        )

def build_application():
    application = ApplicationBuilder().token(TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('ai_status', ai_status))
    application.add_handler(meeting_handler)
    application.add_handler(count_handler)
    application.add_handler(CommandHandler('add', admin_only(add_member)))
    application.add_handler(CommandHandler('remove', admin_only(remove_member)))
    application.add_handler(CommandHandler('list', admin_only(list_members)))

    # Q&A Handler (Text messages that aren't commands) - Allow EVERYONE
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), answer_question))
    return application

if __name__ == '__main__':
    import asyncio
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    application = build_application()

    resolved_webhook_url = WEBHOOK_URL or RENDER_EXTERNAL_URL
    if resolved_webhook_url:
        base = resolved_webhook_url.rstrip("/")
        webhook_path = f"/webhook/{WEBHOOK_SECRET}"
        full_webhook_url = f"{base}{webhook_path}"
        listen_port = int(os.getenv("PORT", str(PORT)))

        print(f"Bot is running in WEBHOOK mode on port {listen_port}...")
        print(f"Webhook endpoint path: {webhook_path}")

        application.run_webhook(
            listen="0.0.0.0",
            port=listen_port,
            url_path=webhook_path.lstrip("/"),
            webhook_url=full_webhook_url,
            drop_pending_updates=True
        )
    else:
        print("Bot is running in POLLING mode...")
        application.run_polling()
