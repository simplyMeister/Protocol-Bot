from telegram import Update
from telegram.ext import ContextTypes
from modules.utils import load_members_from_excel

async def add_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 **Member Management**\n\n"
        "To add a new member, please add their details to **HOSPITALITY MEMBERS.xlsx** on the host machine. "
        "The bot will automatically pick up changes from the Excel file."
    )

async def remove_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 **Member Management**\n\n"
        "To remove a member, please delete their row from **HOSPITALITY MEMBERS.xlsx** on the host machine."
    )

async def list_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    members = load_members_from_excel()
    if members:
        # Group by Hall for better readability
        halls = {}
        for m in members:
            h = m['hall'] or "No Hall"
            if h not in halls: halls[h] = []
            
            # Format name with telegram handle if available
            handle = m.get('telegram_handle')
            if handle:
                clean_handle = handle[1:] if handle.startswith('@') else handle
                name_str = f"{m['name']} (@{clean_handle})"
            else:
                name_str = m['name']
            halls[h].append(name_str)
            
        text = "📋 **Current Protocol Members** (from HOSPITALITY MEMBERS.xlsx)\n\n"
        for hall, names in halls.items():
            text += f"**{hall}**:\n"
            text += "\n".join([f"• {name}" for name in sorted(names)])
            text += "\n\n"
            
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ No members found in HOSPITALITY MEMBERS.xlsx. Please check the file.")

