import os
from dotenv import load_dotenv
from functools import wraps

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PORT = int(os.getenv("PORT", "10000"))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "protocol-bot-webhook")

if not TOKEN:
    raise ValueError("No TELEGRAM_BOT_TOKEN found in environment variables.")

def is_admin(user_id):
    """Check if a user ID is in the admin list."""
    return user_id in ADMIN_IDS

def admin_only(func):
    @wraps(func)
    async def wrapped(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if is_admin(user_id):
            return await func(update, context, *args, **kwargs)
        return
    return wrapped
