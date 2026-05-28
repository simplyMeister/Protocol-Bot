from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters
)
from modules.reports import generate_daily_report
from modules.utils import load_weekly_roster
from config import admin_only
import datetime

# ── Conversation states ──────────────────────────────────────────────────────
(
    PREPARED_BY,
    COUNT_FEMALE,
    COUNT_MALE,
    SATURDAY_COUNTS,
    DUTY_NAME,
    DUTY_TIME,
    DUTY_STATUS,
    DUTY_REASON,
    SERVICE_OVERVIEW,
    CHALLENGES,
    WORKFLOW,
) = range(11)

# Maps duty role display name → roster assignment key
ROLE_TO_ROSTER_KEY = {
    "Entrance Allocation":        "Entrance Allocation",
    "Tag Allocation":             "Tag Allocation",
    "Counting during Pre-service":"Counting",
    "Tag Collector 1":            "Tag Collection",
    "Tag Collector 2":            "Tag Collection",
    "Counting during Hospi-Pray":  "Counting",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_assignments(day_name: str) -> dict:
    """Load this week's roster assignments for the given day."""
    roster_data = load_weekly_roster()
    roster = roster_data.get("roster", {})
    service_map = {
        "Thursday": "Thursday Chapel",
        "Sunday":   ["Sunday Omega", "Sunday Alpha"],
        "Tuesday":  "Tuesday Chapel",
    }
    assignments: dict = {}
    if day_name in service_map:
        keys = service_map[day_name]
        if isinstance(keys, list):
            for key in keys:
                for role, members in roster.get(key, {}).items():
                    if role not in assignments:
                        assignments[role] = []
                    assignments[role].extend(members)
        else:
            assignments = roster.get(keys, {})
    return assignments


async def _ask_duty_name(message, context: ContextTypes.DEFAULT_TYPE):
    """Send the name-prompt for the current duty role."""
    step = context.user_data["duty_step"]
    duty_roles = context.user_data["duty_roles"]
    role = duty_roles[step]

    assignments = context.user_data["report_data"].get("assignments", {})
    roster_key  = ROLE_TO_ROSTER_KEY.get(role, role)
    assigned    = assignments.get(roster_key, [])
    
    # Pre-fill specific hints for Tag Collectors
    if role == "Tag Collector 1" and len(assigned) > 0:
        hint = f"\n_(Rostered: {assigned[0]})_"
    elif role == "Tag Collector 2" and len(assigned) > 1:
        hint = f"\n_(Rostered: {assigned[1]})_"
    else:
        hint = f"\n_(Rostered: {', '.join(assigned)})_" if assigned else ""

    context.user_data["current_duty"] = {"role": role}

    await message.reply_text(
        f"📋 *Role {step + 1}/{len(duty_roles)}: {role}*{hint}\n\n"
        f"Who served as *{role}*? (Enter their name)",
        parse_mode="Markdown",
    )
    return DUTY_NAME


async def _save_and_next(message, context: ContextTypes.DEFAULT_TYPE):
    """Append the completed duty entry and move to the next role or Overview."""
    duty = context.user_data.pop("current_duty")
    context.user_data["duty_table"].append(duty)
    context.user_data["duty_step"] += 1
    step = context.user_data["duty_step"]
    duty_roles = context.user_data["duty_roles"]

    if step < len(duty_roles):
        return await _ask_duty_name(message, context)

    # All roles collected — store and advance to Service Overview
    context.user_data["report_data"]["duty_table"] = context.user_data.pop("duty_table", [])
    await message.reply_text(
        "✅ *Duty table complete!*\n\n"
        "Now, please provide a brief *Service Overview*:\n"
        "_(Describe the overall flow of the service unit during pre-service and "
        "inside the service, including performance of protocol members on duty.)_",
        parse_mode="Markdown",
    )
    return SERVICE_OVERVIEW


# ── Entry point ───────────────────────────────────────────────────────────────

@admin_only
async def start_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the daily count/report flow."""
    context.user_data["report_data"] = {}
    now      = datetime.datetime.now()
    day_name = now.strftime("%A")
    context.user_data["report_data"]["day_name"] = day_name
    context.user_data["report_data"]["date"]     = now.strftime("%A, %d/%m/%Y")

    await update.message.reply_text(
        "📊 *Daily Report Generation*\n\nPlease enter your name (*Prepared by*):",
        parse_mode="Markdown",
    )
    return PREPARED_BY


# ── State handlers ────────────────────────────────────────────────────────────

async def get_prepared_by(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Collect prepared-by name then branch on day."""
    context.user_data["report_data"]["prepared_by"] = update.message.text.strip()
    day_name = context.user_data["report_data"]["day_name"]

    if day_name == "Saturday":
        await update.message.reply_text(
            "🗓 *Saturday Meetings*\n\n"
            "Please enter the counts for *General Meeting* (format: `Male, Female`):",
            parse_mode="Markdown",
        )
        context.user_data["saturday_step"] = "general"
        return SATURDAY_COUNTS
    else:
        await update.message.reply_text(
            "Enter the number of *Female* present:", parse_mode="Markdown"
        )
        return COUNT_FEMALE


async def get_female_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Collect female count."""
    try:
        count = int(update.message.text.strip())
        context.user_data["report_data"]["female"] = count
        await update.message.reply_text(
            "Enter the number of *Male* present:", parse_mode="Markdown"
        )
        return COUNT_MALE
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
        return COUNT_FEMALE


async def get_male_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Collect male count, load assignments, then start duty table Q&A."""
    try:
        count  = int(update.message.text.strip())
        female = context.user_data["report_data"]["female"]
        total  = count + female

        context.user_data["report_data"]["male"]  = count
        context.user_data["report_data"]["total"] = total

        # Load roster for pre-fill hints
        day_name    = context.user_data["report_data"]["day_name"]
        assignments = _load_assignments(day_name)
        context.user_data["report_data"]["assignments"] = assignments

        # ── Determine duty roles dynamically based on the day ──────────────
        if day_name == "Friday":
            duty_roles = ["Counting during Hospi-Pray"]
        else:
            # Sun / Tue / Thu and any other service day
            duty_roles = [
                "Entrance Allocation",
                "Tag Allocation",
                "Counting during Pre-service",
                "Tag Collector 1",
                "Tag Collector 2",
            ]
        context.user_data["duty_roles"] = duty_roles

        # Initialise duty table state
        context.user_data["duty_table"] = []
        context.user_data["duty_step"]  = 0

        await update.message.reply_text(
            f"✅ *Total Count: {total}*\n\n"
            "Now let's fill in the *Duty Table* 📋\n"
            "I'll ask about each protocol role one by one.",
            parse_mode="Markdown",
        )
        return await _ask_duty_name(update.message, context)

    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
        return COUNT_MALE


async def get_duty_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store name for current role and ask arrival time."""
    name = update.message.text.strip()
    context.user_data["current_duty"]["name"] = name
    role = context.user_data["current_duty"]["role"]

    await update.message.reply_text(
        f"⏰ What time did *{name}* arrive for *{role}*?\n_(e.g. `7:30am`, `8:15am`)_",
        parse_mode="Markdown",
    )
    return DUTY_TIME


async def get_duty_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store arrival time and ask present/absent via inline buttons."""
    context.user_data["current_duty"]["time"] = update.message.text.strip()
    name = context.user_data["current_duty"]["name"]
    role = context.user_data["current_duty"]["role"]

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Present", callback_data="duty_present"),
        InlineKeyboardButton("❌ Absent",  callback_data="duty_absent"),
    ]])

    await update.message.reply_text(
        f"Was *{name}* present or absent for *{role}*?",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    return DUTY_STATUS


async def get_duty_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the Present / Absent inline button press."""
    query = update.callback_query
    await query.answer()

    status = "Present" if query.data == "duty_present" else "Absent"
    context.user_data["current_duty"]["status"] = status
    context.user_data["current_duty"]["reason"] = ""

    if status == "Absent":
        name = context.user_data["current_duty"]["name"]
        await query.edit_message_text(
            f"❓ What is the reason for *{name}'s* absence?",
            parse_mode="Markdown",
        )
        return DUTY_REASON
    else:
        await query.edit_message_text("✅ Marked as *Present*.", parse_mode="Markdown")
        return await _save_and_next(query.message, context)


async def get_duty_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store absence reason then advance to next role."""
    context.user_data["current_duty"]["reason"] = update.message.text.strip()
    return await _save_and_next(update.message, context)


async def get_saturday_counts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Collect counts for Saturday's 4 meetings."""
    try:
        text  = update.message.text.strip()
        parts = [p.strip() for p in text.split(",")]
        if len(parts) != 2:
            raise ValueError()

        male, female = int(parts[0]), int(parts[1])
        data = {"male": male, "female": female, "total": male + female}
        step = context.user_data.get("saturday_step", "general")

        if step == "general":
            context.user_data["report_data"]["general_meeting"] = data
            context.user_data["saturday_step"] = "chaplaincy"
            await update.message.reply_text(
                "Enter counts for *Chaplaincy Meeting* (format: `Male, Female`):",
                parse_mode="Markdown",
            )
            return SATURDAY_COUNTS

        elif step == "chaplaincy":
            context.user_data["report_data"]["chaplaincy_meeting"] = data
            context.user_data["saturday_step"] = "chop"
            await update.message.reply_text(
                "Enter counts for *CHOP* (format: `Male, Female`):",
                parse_mode="Markdown",
            )
            return SATURDAY_COUNTS

        elif step == "chop":
            context.user_data["report_data"]["chop"] = data
            context.user_data["saturday_step"] = "word_feast"
            await update.message.reply_text(
                "Enter counts for *WORD FEAST* (format: `Male, Female`):",
                parse_mode="Markdown",
            )
            return SATURDAY_COUNTS

        elif step == "word_feast":
            context.user_data["report_data"]["word_feast"] = data
            await update.message.reply_text(
                "✅ All Saturday counts recorded.\n\n"
                "Now, please provide a brief *Service Overview*:",
                parse_mode="Markdown",
            )
            return SERVICE_OVERVIEW

    except ValueError:
        await update.message.reply_text(
            "❌ Please enter valid numbers in format: `Male, Female` (e.g., `10, 20`)"
        )
        return SATURDAY_COUNTS


async def get_service_overview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Collect service overview."""
    context.user_data["report_data"]["service_overview"] = update.message.text

    await update.message.reply_text(
        "Please list any *Challenges & Incidents*:\n"
        "_(List any obstacles faced during subunit duties or specific incidents "
        "in the pre-service and service that required attention. "
        "Type 'None' if there were no challenges.)_",
        parse_mode="Markdown",
    )
    return CHALLENGES


async def get_challenges(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Collect challenges and incidents."""
    context.user_data["report_data"]["challenges"] = update.message.text

    await update.message.reply_text(
        "Finally, please provide *Workflow Suggestions*:\n"
        "_(Based on today's experience, what could be improved for next time? "
        "Type 'None' if no suggestions.)_",
        parse_mode="Markdown",
    )
    return WORKFLOW


async def get_workflow_suggestions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Collect workflow suggestions and generate the Word report."""
    context.user_data["report_data"]["workflow_suggestions"] = update.message.text

    await update.message.reply_text("⏳ Generating daily report from template...")

    try:
        report_path = generate_daily_report(context.user_data["report_data"])
        with open(report_path, "rb") as f:
            now = datetime.datetime.now()
            await update.message.reply_document(
                document=f,
                filename=f"Daily_Report_{now.strftime('%Y%m%d')}.docx",
                caption="✅ Daily report generated successfully!",
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Error generating report: {e}")

    return ConversationHandler.END


async def cancel_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the report flow."""
    await update.message.reply_text("❌ Daily report cancelled.")
    return ConversationHandler.END


# ── Conversation handler registration ─────────────────────────────────────────
count_handler = ConversationHandler(
    entry_points=[CommandHandler("count", start_count)],
    states={
        PREPARED_BY:     [MessageHandler(filters.TEXT & ~filters.COMMAND, get_prepared_by)],
        COUNT_FEMALE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, get_female_count)],
        COUNT_MALE:      [MessageHandler(filters.TEXT & ~filters.COMMAND, get_male_count)],
        SATURDAY_COUNTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_saturday_counts)],
        DUTY_NAME:       [MessageHandler(filters.TEXT & ~filters.COMMAND, get_duty_name)],
        DUTY_TIME:       [MessageHandler(filters.TEXT & ~filters.COMMAND, get_duty_time)],
        DUTY_STATUS:     [CallbackQueryHandler(get_duty_status, pattern="^duty_(present|absent)$")],
        DUTY_REASON:     [MessageHandler(filters.TEXT & ~filters.COMMAND, get_duty_reason)],
        SERVICE_OVERVIEW:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_service_overview)],
        CHALLENGES:      [MessageHandler(filters.TEXT & ~filters.COMMAND, get_challenges)],
        WORKFLOW:        [MessageHandler(filters.TEXT & ~filters.COMMAND, get_workflow_suggestions)],
    },
    fallbacks=[CommandHandler("cancel", cancel_count)],
)
