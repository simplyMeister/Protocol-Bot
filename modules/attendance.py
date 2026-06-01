from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from modules.utils import load_members_from_excel, save_weekly_roster, load_roster_history, save_roster_history
from config import admin_only
import datetime
import random

# States
ATTENDANCE, CONFIRM_ROSTER, CONFIRM_NOTIFICATIONS, SELECT_DAY, SELECT_ROLE, SELECT_MEMBER, SWAP_MEMBER = range(7)

# Hall Configuration
OMEGA_HALLS = ["JOSEPH", "PETER", "DORCAS", "MARY"]
ALPHA_HALLS = ["LYDIA", "DANIEL", "JOHN", "PAUL", "DEBORAH"]

ROLES = ["Entrance Allocation", "Tag Allocation", "Counting", "Tag Collection"]

ROLE_SLOTS = {
    "Entrance Allocation": 1,
    "Tag Allocation": 1,
    "Counting": 1,
    "Tag Collection": 2
}

def get_next_service_dates():
    """Calculate the dates for the upcoming service cycle (Thu to next Tue)"""
    today = datetime.datetime.now()
    dates = {}
    
    # Target days: Thu, Sun, Sun, Tue
    
    def get_next_weekday(start_date, weekday):
        days_ahead = weekday - start_date.weekday()
        if days_ahead < 0: # Target day already happened this week
            days_ahead += 7
        return start_date + datetime.timedelta(days_ahead)

    thu = get_next_weekday(today, 3)    # Thursday
    sun = get_next_weekday(thu, 6)    # Sunday
    tue = get_next_weekday(sun, 1)    # Tuesday
    
    dates["Thursday Chapel"] = thu.strftime("%Y-%m-%d")
    dates["Sunday Omega"] = sun.strftime("%Y-%m-%d")
    dates["Sunday Alpha"] = sun.strftime("%Y-%m-%d")
    dates["Tuesday Chapel"] = tue.strftime("%Y-%m-%d")
    
    return dates


@admin_only
async def start_meeting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the meeting attendance flow"""
    context.user_data['attendance'] = set()
    
    # Load all members from Excel
    all_members = load_members_from_excel()
    context.user_data['all_members'] = all_members
    
    if not all_members:
        await update.message.reply_text("No members found in HOSPITALITY MEMBERS.xlsx. Please check the file.")
        return ConversationHandler.END
    
    await show_attendance_keyboard(update.message, context)
    return ATTENDANCE

def _member_matches_query(name: str, query: str) -> bool:
    return query in name.lower()


async def show_attendance_keyboard(message, context, subtitle=None):
    """Display attendance selection keyboard (full list or search results)."""
    members = context.user_data["all_members"]
    present = context.user_data["attendance"]
    search_query = context.user_data.get("attendance_search_query")

    now = datetime.datetime.now()
    date_str = now.strftime("%A, %d/%m/%Y at %H:%M")

    sorted_members = sorted(members, key=lambda x: x["name"])
    if search_query:
        sorted_members = [
            m for m in sorted_members
            if _member_matches_query(m["name"], search_query)
        ]

    keyboard = []
    for member in sorted_members[:20]:
        name = member["name"]
        status = "✅" if name in present else "❌"
        keyboard.append([InlineKeyboardButton(f"{status} {name}", callback_data=f"toggle_{name}")])

    if search_query and len(sorted_members) > 20:
        keyboard.append([
            InlineKeyboardButton(f"… and {len(sorted_members) - 20} more — refine search", callback_data="attendance_search")
        ])

    keyboard.append([InlineKeyboardButton("🔍 Search by name", callback_data="attendance_search")])
    if search_query:
        keyboard.append([InlineKeyboardButton("◀ Show all members", callback_data="attendance_show_all")])
    keyboard.append([InlineKeyboardButton("✓ Done", callback_data="done_attendance")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    present_count = len(present)
    text = f"📋 **Attendance for today's meeting**\n{date_str}\n\nPresent: **{present_count}**"
    if subtitle:
        text += f"\n{subtitle}"
    if search_query:
        text += f"\n\nShowing matches for: `{search_query}` ({len(sorted_members)} found)"
    if not sorted_members:
        text += "\n\n_No members matched. Tap Search again or Show all._"

    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception:
        await message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def handle_attendance_search_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin typed a name to search during attendance."""
    if not context.user_data.get("awaiting_attendance_search"):
        return ATTENDANCE

    query_text = update.message.text.strip()
    if not query_text:
        await update.message.reply_text("Please type at least one letter of the member's name.")
        return ATTENDANCE

    context.user_data["awaiting_attendance_search"] = False
    context.user_data["attendance_search_query"] = query_text.lower()

    matches = [
        m for m in context.user_data["all_members"]
        if _member_matches_query(m["name"], query_text.lower())
    ]

    if not matches:
        context.user_data["awaiting_attendance_search"] = True
        await update.message.reply_text(
            f"No member found matching **{query_text}**.\nType another name to search.",
            parse_mode="Markdown",
        )
        return ATTENDANCE

    await show_attendance_keyboard(
        update.message,
        context,
        subtitle=f"Found **{len(matches)}** match(es). Tap to mark present/absent.",
    )
    return ATTENDANCE


async def handle_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle attendance toggle and completion"""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "attendance_search":
        context.user_data["awaiting_attendance_search"] = True
        await query.edit_message_text(
            "🔍 **Search by name**\n\nType part of the member's name below (e.g. `Buchi`).",
            parse_mode="Markdown",
        )
        return ATTENDANCE

    if data == "attendance_show_all":
        context.user_data["awaiting_attendance_search"] = False
        context.user_data.pop("attendance_search_query", None)
        await show_attendance_keyboard(query.message, context)
        return ATTENDANCE

    if data == "done_attendance":
        if not context.user_data['attendance']:
            await query.edit_message_text("❌ No members marked present. Meeting cancelled.")
            return ConversationHandler.END
        
        # Store attendance with timestamp
        context.user_data['meeting_date'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Ask about roster generation
        keyboard = [
            [InlineKeyboardButton("✅ Yes", callback_data="roster_yes")],
            [InlineKeyboardButton("❌ No", callback_data="roster_no")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Do you want to generate the names for **Entrance Allocation, Tag Allocation, Tag Collection, and Counting** "
            "for this week?",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return CONFIRM_ROSTER
    
    if data.startswith("toggle_"):
        name = data.replace("toggle_", "")
        present = context.user_data['attendance']
        if name in present:
            present.remove(name)
        else:
            present.add(name)
        await show_attendance_keyboard(query.message, context)
        return ATTENDANCE

import logging

logger = logging.getLogger(__name__)

async def handle_roster_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle roster generation confirmation"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "roster_no":
        await query.edit_message_text("✅ Attendance recorded. No roster generated.")
        return ConversationHandler.END
    
    # Generate weekly roster
    await query.edit_message_text("⏳ Generating fair weekly roster...")
    
    present_members = list(context.user_data['attendance'])
    all_members_data = {m['name']: m for m in context.user_data['all_members']}
    
    service_dates = get_next_service_dates()
    history = load_roster_history()
    
    roster = generate_weekly_roster(present_members, all_members_data, history)
    
    # Update history with new assignments
    for service, assignments in roster.items():
        if service not in history:
            history[service] = []
        newly_assigned = []
        for role_members in assignments.values():
            newly_assigned.extend(role_members)
        history[service] = newly_assigned 

    save_roster_history(history)
    
    # Save roster
    save_weekly_roster({
        'generated_date': context.user_data['meeting_date'],
        'service_dates': service_dates,
        'roster': roster
    })
    
    # Format and display roster
    message = format_roster_message(roster, service_dates, all_members_data)
    await query.message.reply_text(message, parse_mode="Markdown")
    
    # Store for notifications
    context.user_data['last_roster'] = roster
    context.user_data['last_service_dates'] = service_dates

    # Ask about sending notifications
    keyboard = [
        [InlineKeyboardButton("✅ Yes, Send them", callback_data="notif_yes")],
        [InlineKeyboardButton("✏️ Edit Roster", callback_data="edit_roster")],
        [InlineKeyboardButton("❌ No, Just Save", callback_data="notif_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(
        "Roaster saved. Do you want to send **personalized notifications** to the members now?",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    
    return CONFIRM_NOTIFICATIONS

async def handle_notification_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle notification confirmation"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "notif_no":
        await query.edit_message_text("✅ Roster saved. No notifications sent.")
        return ConversationHandler.END
    
    await query.edit_message_text("⏳ Sending notifications to members...")
    
    roster = context.user_data.get('last_roster')
    service_dates = context.user_data.get('last_service_dates')
    all_members_data = {m['name']: m for m in context.user_data['all_members']}

    if roster and service_dates:
        sent, failed, no_id = await send_notifications(roster, service_dates, all_members_data, context)
        
        summary = f"📬 **Notification Summary**\n\n"
        
        summary += f"✅ **Successfully sent ({len(sent)}):**\n"
        if sent:
            summary += "\n".join([f"• {m}" for m in sent]) + "\n"
        else:
            summary += "_None_\n"
            
        summary += f"\n⚠️ **Failed (bot not started/blocked) ({len(failed)}):**\n"
        if failed:
            summary += "\n".join([f"• {m}" for m in failed]) + "\n"
        else:
            summary += "_None_\n"
            
        summary += f"\nℹ️ **No Telegram ID in Excel ({len(no_id)}):**\n"
        if no_id:
            summary += "\n".join([f"• {m}" for m in sorted(no_id)]) + "\n"
        else:
            summary += "_None_\n"
            
        await query.message.reply_text(summary, parse_mode="Markdown")
    else:
        await query.message.reply_text("❌ Error: Could not retrieve roster data for notifications.")
            
    return ConversationHandler.END

def get_day_suffix(day):
    if 11 <= day <= 13:
        return 'th'
    else:
        return {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')

async def send_notifications(roster, service_dates, all_members_data, context):
    """
    Send consolidated personalized notifications to all members in the roster.
    Returns (sent_members, failed_members, no_id_members) containing formatted strings with handles.
    """
    # Build a mapping: name -> { telegram_id, tasks }
    name_assignments = {}
    no_id_names = set()

    for service, assignments in roster.items():
        date_str = service_dates.get(service, "TBD")
        try:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            day = dt.day
            suffix = get_day_suffix(day)
            pretty_date = dt.strftime(f"%A {day}{suffix} %B %Y")
        except:
            pretty_date = date_str
            
        for role, members in assignments.items():
            for name in members:
                member_data = all_members_data.get(name, {})
                raw_tid = member_data.get('telegram_id')
                
                # Safely cast telegram_id to int (it may come as float from pandas)
                telegram_id = None
                if raw_tid is not None:
                    try:
                        telegram_id = int(raw_tid)
                    except (ValueError, TypeError):
                        telegram_id = None
                
                if telegram_id:
                    if name not in name_assignments:
                        name_assignments[name] = {"telegram_id": telegram_id, "tasks": []}
                    name_assignments[name]["tasks"].append((role, pretty_date))
                else:
                    no_id_names.add(name)

    sent_members = []
    failed_members = []

    def format_name_with_handle(name):
        member_data = all_members_data.get(name, {})
        handle = member_data.get('telegram_handle')
        if handle:
            clean_handle = handle[1:] if handle.startswith('@') else handle
            return f"{name} @{clean_handle}"
        return name

    no_id_members = [format_name_with_handle(name) for name in no_id_names]

    # Send one consolidated message per member
    for name, data in name_assignments.items():
        telegram_id = data["telegram_id"]
        tasks = data["tasks"]
        
        if not tasks:
            continue
            
        formatted_tasks = [f"{role.lower()} for {date}" for role, date in tasks]
        
        if len(formatted_tasks) == 1:
            task_text = formatted_tasks[0]
        else:
            task_text = " and you'd be handling ".join(formatted_tasks)
            
        notif_msg = (
            f"Dear {name}, Fortune Greetings! Please be informed that you are handling "
            f"{task_text}. Thank you."
        )
        
        formatted_name = format_name_with_handle(name)
        try:
            await context.bot.send_message(chat_id=telegram_id, text=notif_msg)
            sent_members.append(formatted_name)
            logger.info(f"Notification sent to {name} ({telegram_id})")
        except Exception as e:
            failed_members.append(formatted_name)
            logger.error(f"Failed to send notification to {name} ({telegram_id}): {e}")
    
    return sent_members, failed_members, no_id_members


def generate_weekly_roster(present_members, all_members_data, history):
    """
    Generate weekly roster with strict slots, weekly single-assignment, and fallback to absent members.
    Role slot limits:
    - Entrance Allocation: 1 name
    - Tag Allocation: 1 name
    - Counting: 1 name
    - Tag Collection: 2 names
    Once a member is assigned to any role in any service this week, they won't
    appear again until all other eligible candidates are exhausted.
    Priority order:
    1. Present, not yet assigned this week, did NOT serve in this service last time
    2. Present, not yet assigned this week, DID serve in this service last time
    3. Absent, not yet assigned this week, did NOT serve in this service last time
    4. Absent, not yet assigned this week, DID serve in this service last time
    5. Present, already assigned this week, did NOT serve in this service last time
    6. Present, already assigned this week, DID serve in this service last time
    7. Absent, already assigned this week, did NOT serve in this service last time
    8. Absent, already assigned this week, DID serve in this service last time
    """
    roster = {}
    service_days = ["Thursday Chapel", "Sunday Omega", "Sunday Alpha", "Tuesday Chapel"]
    
    # Identify absent members from the full member list
    present_set = set(present_members)
    absent_members = [name for name in all_members_data.keys() if name not in present_set]
    
    # Track members assigned anywhere across the entire week
    weekly_assigned = set()
    
    for service in service_days:
        # Filter eligible present and absent members based on service requirements (college/hall)
        present_eligible = filter_members_for_service(service, present_members, all_members_data)
        absent_eligible = filter_members_for_service(service, absent_members, all_members_data)
        
        # Get history for this service
        last_served = set(history.get(service, []))
        
        # --- 8-tier priority pools (each group shuffled for variety) ---
        # Tier 1: Present, NOT yet assigned this week, did NOT serve last time
        t1 = [m for m in present_eligible if m not in weekly_assigned and m not in last_served]
        random.shuffle(t1)
        # Tier 2: Present, NOT yet assigned this week, DID serve last time
        t2 = [m for m in present_eligible if m not in weekly_assigned and m in last_served]
        random.shuffle(t2)
        # Tier 3: Absent, NOT yet assigned this week, did NOT serve last time
        t3 = [m for m in absent_eligible if m not in weekly_assigned and m not in last_served]
        random.shuffle(t3)
        # Tier 4: Absent, NOT yet assigned this week, DID serve last time
        t4 = [m for m in absent_eligible if m not in weekly_assigned and m in last_served]
        random.shuffle(t4)
        # Tier 5: Present, already assigned this week, did NOT serve last time
        t5 = [m for m in present_eligible if m in weekly_assigned and m not in last_served]
        random.shuffle(t5)
        # Tier 6: Present, already assigned this week, DID serve last time
        t6 = [m for m in present_eligible if m in weekly_assigned and m in last_served]
        random.shuffle(t6)
        # Tier 7: Absent, already assigned this week, did NOT serve last time
        t7 = [m for m in absent_eligible if m in weekly_assigned and m not in last_served]
        random.shuffle(t7)
        # Tier 8: Absent, already assigned this week, DID serve last time
        t8 = [m for m in absent_eligible if m in weekly_assigned and m in last_served]
        random.shuffle(t8)
        
        prioritized_candidates = t1 + t2 + t3 + t4 + t5 + t6 + t7 + t8
        
        # Track who is already assigned for THIS service day (prevents double-role within one service)
        already_assigned_today = set()
        
        # Assign roles with strict slot counts
        service_assignments = {}
        for role in ROLES:
            slots_needed = ROLE_SLOTS.get(role, 1)
            
            # Only pick candidates not already used today
            candidates = [m for m in prioritized_candidates if m not in already_assigned_today]
            
            assigned = candidates[:slots_needed]
            service_assignments[role] = assigned
            already_assigned_today.update(assigned)
            weekly_assigned.update(assigned)
            
        roster[service] = service_assignments
        
    return roster

def filter_members_for_service(service, present_members, all_members_data):
    """Filter members based on college/hall requirements for each service"""
    eligible = []
    
    for name in present_members:
        member_data = all_members_data.get(name, {})
        college = member_data.get('college', '').strip().upper()
        hall = member_data.get('hall', '').strip().upper()
        
        if service == "Tuesday Chapel":
            if college in ["COE", "CLDS"]: eligible.append(name)
        elif service == "Thursday Chapel":
            if college in ["CST", "CMSS"]: eligible.append(name)
        elif service == "Sunday Alpha":
            if hall in ALPHA_HALLS: eligible.append(name)
        elif service == "Sunday Omega":
            if hall in OMEGA_HALLS: eligible.append(name)
    return eligible

def format_roster_message(roster, service_dates, all_members_data):
    """Format roster for display with dates and Telegram handles"""
    def format_name_with_handle(name):
        member_data = all_members_data.get(name, {})
        handle = member_data.get('telegram_handle')
        if handle:
            clean_handle = handle[1:] if handle.startswith('@') else handle
            # Escape underscore to keep Markdown output readable for handles like @type_jc
            escaped_handle = clean_handle.replace("_", "\\_")
            return f"{name} @{escaped_handle}"
        return name

    message = "📅 **WEEKLY ROSTER GENERATED**\n\n"
    
    service_days = ["Thursday Chapel", "Sunday Omega", "Sunday Alpha", "Tuesday Chapel"]
    
    for service in service_days:
        date_str = service_dates.get(service, "TBD")
        # Prettier date
        try:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            pretty_date = dt.strftime("%A, %d/%m/%Y")
        except:
            pretty_date = date_str
            
        message += f"🗓 **{pretty_date}**\n_{service}_\n"
        assignments = roster.get(service, {})
        
        for role in ROLES:
            members = assignments.get(role, [])
            if members:
                formatted_members = [format_name_with_handle(name) for name in members]
                message += f"  • {role}: {', '.join(formatted_members)}\n"
            else:
                message += f"  • {role}: (None assigned)\n"
        message += "\n"
    
    return message

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Meeting cancelled.")
    return ConversationHandler.END

# --- Roster Editing Handlers ---

async def handle_edit_roster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show service days to edit"""
    query = update.callback_query
    await query.answer()
    
    service_days = ["Thursday Chapel", "Sunday Omega", "Sunday Alpha", "Tuesday Chapel"]
    keyboard = [[InlineKeyboardButton(day, callback_data=f"edit_day_{day}")] for day in service_days]
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="edit_back_main")])
    
    await query.edit_message_text("Select the **Service Day** to edit:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return SELECT_DAY

async def handle_day_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show roles for selected day"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "edit_back_main":
        # Go back to main roster confirmation
        keyboard = [
            [InlineKeyboardButton("✅ Yes, Send them", callback_data="notif_yes")],
            [InlineKeyboardButton("✏️ Edit Roster", callback_data="edit_roster")],
            [InlineKeyboardButton("❌ No, Just Save", callback_data="notif_no")]
        ]
        await query.edit_message_text(
            "Roaster saved. Do you want to send **personalized notifications** to the members now?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return CONFIRM_NOTIFICATIONS

    day = query.data.replace("edit_day_", "")
    context.user_data['edit_day'] = day
    
    keyboard = [[InlineKeyboardButton(role, callback_data=f"edit_role_{role}")] for role in ROLES]
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="edit_roster")])
    
    await query.edit_message_text(f"Day: **{day}**\nSelect the **Role** to edit:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return SELECT_ROLE

async def handle_role_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show members currently in the role"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "edit_roster":
        return await handle_edit_roster(update, context)

    role = query.data.replace("edit_role_", "")
    context.user_data['edit_role'] = role
    day = context.user_data['edit_day']
    
    roster = context.user_data['last_roster']
    assigned_members = roster.get(day, {}).get(role, [])
    
    if not assigned_members:
        await query.answer("No members assigned to this role.", show_alert=True)
        # Just stay here but show roles again? Or maybe allow adding?
        # For now, just allow them to go back.
        return SELECT_ROLE

    keyboard = [[InlineKeyboardButton(name, callback_data=f"edit_mem_{name}")] for name in assigned_members]
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data=f"edit_day_{day}")])
    
    await query.edit_message_text(f"Role: **{role}**\nSelect the **Member** you want to swap:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return SELECT_MEMBER

async def handle_member_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show present members to swap with"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("edit_day_"):
        return await handle_day_selection(update, context)

    old_name = query.data.replace("edit_mem_", "")
    context.user_data['edit_old_name'] = old_name
    
    present_members = sorted(list(context.user_data['attendance']))
    
    keyboard = []
    # Show all present members (including those assigned elsewhere, as user might want to swap)
    for name in present_members:
        if name == old_name: continue
        keyboard.append([InlineKeyboardButton(name, callback_data=f"swap_with_{name}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data=f"edit_role_{context.user_data['edit_role']}")])
    
    await query.edit_message_text(f"Swap **{old_name}** with:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return SWAP_MEMBER

async def handle_swap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Perform the swap and show updated roster"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("edit_role_"):
        return await handle_role_selection(update, context)

    new_name = query.data.replace("swap_with_", "")
    old_name = context.user_data['edit_old_name']
    day = context.user_data['edit_day']
    role = context.user_data['edit_role']
    
    roster = context.user_data['last_roster']
    
    # Perform swap in the roster
    # Note: If new_name was assigned to another role, what happens? 
    # Usually we just replace old_name with new_name in THIS role.
    # If the user wants a full swap, they can do it in two steps.
    
    current_assigned = roster[day][role]
    updated_assigned = [new_name if name == old_name else name for name in current_assigned]
    roster[day][role] = updated_assigned
    
    context.user_data['last_roster'] = roster
    
    # Save updated roster
    service_dates = context.user_data['last_service_dates']
    save_weekly_roster({
        'generated_date': context.user_data['meeting_date'],
        'service_dates': service_dates,
        'roster': roster
    })
    
    await query.message.reply_text(f"✅ Swapped **{old_name}** for **{new_name}** in {role}.")
    
    # Show updated roster summary and confirmation again
    all_members_data = {m['name']: m for m in context.user_data['all_members']}
    message = format_roster_message(roster, service_dates, all_members_data)
    await query.message.reply_text(message, parse_mode="Markdown")
    
    keyboard = [
        [InlineKeyboardButton("✅ Yes, Send them", callback_data="notif_yes")],
        [InlineKeyboardButton("✏️ Edit Roster", callback_data="edit_roster")],
        [InlineKeyboardButton("❌ No, Just Save", callback_data="notif_no")]
    ]
    await query.message.reply_text(
        "Roaster updated. Send notifications?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return CONFIRM_NOTIFICATIONS

# --- End Roster Editing Handlers ---

# Conversation handler
meeting_handler = ConversationHandler(
    entry_points=[CommandHandler('meeting', start_meeting)],
    states={
        ATTENDANCE: [
            CallbackQueryHandler(handle_attendance),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_attendance_search_input),
        ],
        CONFIRM_ROSTER: [CallbackQueryHandler(handle_roster_confirmation)],
        CONFIRM_NOTIFICATIONS: [
            CallbackQueryHandler(handle_notification_confirmation, pattern="^notif_.*"),
            CallbackQueryHandler(handle_edit_roster, pattern="^edit_roster$")
        ],
        SELECT_DAY: [CallbackQueryHandler(handle_day_selection)],
        SELECT_ROLE: [CallbackQueryHandler(handle_role_selection)],
        SELECT_MEMBER: [CallbackQueryHandler(handle_member_selection)],
        SWAP_MEMBER: [CallbackQueryHandler(handle_swap)],
    },
    fallbacks=[CommandHandler('cancel', cancel)]
)
