from telegram import Update
from telegram.ext import ContextTypes

import google.generativeai as genai
from config import GEMINI_API_KEY
from modules.protocol_kb import search_protocol_document
import logging
import re
import time

logger = logging.getLogger(__name__)

# Configure Gemini if key is available
AI_AVAILABLE = False
AVAILABLE_MODELS = []
AI_DISABLED_UNTIL = 0
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        AI_AVAILABLE = True
        try:
            # Discover models supported by this key/version to avoid hardcoded 404s.
            for model in genai.list_models():
                name = getattr(model, "name", "")
                methods = getattr(model, "supported_generation_methods", []) or []
                if "generateContent" in methods and "gemini" in name.lower():
                    AVAILABLE_MODELS.append(name.replace("models/", ""))
        except Exception as model_discovery_error:
            logger.warning(f"Could not list Gemini models: {model_discovery_error}")
    except Exception as e:
        logger.error(f"Failed to configure Gemini: {e}")

PROTOCOL_INFO = {
    # ... (same dictionary as before)
    "provost": {
        "title": "Provost",
        "keywords": ["provost", "supervisor", "supervise"],
        "info": "The provost functions as the overall supervisor, ensuring orderliness and that everyone serving as protocol carries out their duties effectively. This supervision begins from the night before the service and continues until all members are properly seated in their assigned hospitality seats during the service. The provost also ensures that Gentleness 03 is reserved for Hospitality.",
        "more": "They are responsible for the overall flow and must ensure Gentleness 03 is strictly protected for executive members."
    },
    "entrance": {
        "title": "Entrance Allocation",
        "keywords": ["entrance", "allocate", "allocation", "seat"],
        "info": "Allocates Hospitality seats to members (03 for executives). Checks compliance (dressing, Bible, pen, ID). Allocation closes 20 mins into pre-service. Confirms all are at posts before service.",
        "more": "Entrance workers must ensure that members are encouraged and that they have all required items (Bible, pen, ID card) before being assigned a seat."
    },
    "tag_allocation": {
        "title": "Tag Allocation",
        "keywords": ["tag", "tags", "allocation"],
        "info": "Gives tags to serving members only (exec/member tags separate). Works with Entrance Allocation. Counts during pre-service for confirmation.",
        "more": "Tags are used to differentiate executives from regular members. Accurate counting during pre-service is vital for seat management."
    },
    "counting": {
        "title": "Counting",
        "keywords": ["counting", "count", "male", "female"],
        "info": "Ensures accurate service counting (separate male/female). Ensures orderly pre-service and concentric prayer circles.",
        "more": "Counters are responsible for the final attendance figures provided in the daily report. They also maintain order during the prayer sessions."
    },
    "collection": {
        "title": "Tag Collection",
        "keywords": ["collection", "collect", "return"],
        "info": "Collects all hospitality tags from every entrance after service. Ensures no one leaves with a tag.",
        "more": "This role is critical to prevent loss of tags. All tags must be accounted for and returned to the provost after the service."
    },
    "ushers": {
        "title": "Ushers / Hospitality Seat Protection",
        "keywords": ["ushers", "usher", "protection", "elevation"],
        "info": "Ushers must protect the hospitality seats on every elevation as it is the seat directly in front of them.",
        "more": "This specifically refers to maintaining the integrity of the protocol seating area throughout the service."
    },
    "student_council": {
        "title": "Student Council / Gentleness",
        "keywords": ["council", "student council", "gentleness", "last row"],
        "info": "To ensure there is more clarity on why we need the entirety of the last row in gentleness to avoid issues, especially on Thursday and Saturdays.",
        "more": "Coordination with the Student Council is necessary to prevent seating conflicts in the 'Gentleness' section."
    },
    "attendance_unit": {
        "title": "Attendance Unit",
        "keywords": ["attendance unit", "altar", "altar left", "altar right", "altar peace"],
        "info": "The Attendance unit must provide attendance to hospitality unit members at Altar Left, Altar Right and Altar Peace, especially for Thursday Services.",
        "more": "This ensures that members serving at the altar positions are properly marked present during meeting sessions."
    },
    "colleges": {
        "title": "Colleges",
        "keywords": ["college", "colleges", "coe", "clds", "cst", "cmss"],
        "info": "Colleges involved: CST (Science & Tech), COE (Engineering), CLDS (Leadership & Dev), CMSS (Management & Social Sciences).",
        "more": "Service days are often assigned based on these colleges (e.g., Tuesday for COE/CLDS, Thursday for CST/CMSS)."
    }
}

SYSTEM_PROMPT = f"""
You are the Protocol Unit Assistant for a church organization. Your task is to answer questions about protocol roles, rules, and procedures accurately and helpfully.

Background Information on Roles:
{str(PROTOCOL_INFO)}

Additional Context:
- The unit involves handling hospitality for members.
- Members must check compliance: Dressing, Bible, Pen, ID Card.
- Gentleness 03 is a specific section reserved for Hospitality/Executives.
- Tags (Executive and Member tags) are used to identify people serving.
- Tuesday Chapel: COE, CLDS colleges.
- Thursday Chapel: CST, CMSS colleges.
- Sunday: Alpha and Omega services.

Guidelines:
1. Be polite and professional.
2. If you don't know the answer, say you don't know but try to relate it to existing protocol rules.
3. Keep answers concise but informative.
4. Handle follow-up questions naturally based on the conversation context.
"""

SCENARIO_PROMPT = """
You are a practical Protocol operations advisor.
Answer ONLY what the user asked — one role or one topic at a time.
If they ask about the Provost, describe only the Provost (do not list Entrance, Tags, Counting, or Collection).
Keep answers concise, specific, and directly tied to their question.
Do not paste long multi-role documents or generic menus.
"""

MODEL_CANDIDATES = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-1.5-flash-8b",
]

async def get_ai_response(text, chat_history):
    global AI_DISABLED_UNTIL
    if not AI_AVAILABLE:
        return None
    if AI_DISABLED_UNTIL and time.time() < AI_DISABLED_UNTIL:
        return None
    
    try:
        model_order = AVAILABLE_MODELS[:] if AVAILABLE_MODELS else MODEL_CANDIDATES[:]
        for model_name in model_order:
            try:
                model = genai.GenerativeModel(
                    model_name,
                    system_instruction=f"{SYSTEM_PROMPT}\n\n{SCENARIO_PROMPT}"
                )
                chat = model.start_chat(history=chat_history)
                response = chat.send_message(
                    text,
                    generation_config={
                        "temperature": 0.85,
                        "top_p": 0.95,
                        "max_output_tokens": 700
                    }
                )
                if response and getattr(response, "text", None):
                    return response.text.strip()
            except Exception as model_error:
                logger.warning(f"Model {model_name} failed: {model_error}")
                error_text = str(model_error).lower()
                # Back off briefly when quota is exceeded to reduce repeated rigid fallbacks.
                if "quota" in error_text or "429" in error_text:
                    retry_match = re.search(r"retry in\s+(\d+(?:\.\d+)?)s", error_text)
                    retry_seconds = float(retry_match.group(1)) if retry_match else 30.0
                    AI_DISABLED_UNTIL = time.time() + retry_seconds
                continue
    except Exception as e:
        logger.error(f"AI response error: {e}")
    return None

FOLLOW_UP_KEYWORDS = ["more", "detail", "else", "what about", "tell me", "continue"]
PROTOCOL_TERMS = [
    "protocol", "provost", "entrance", "tag", "count", "counting", "collection",
    "attendance", "altar", "usher", "hospitality", "gentleness", "pre-service",
    "service", "chapel", "sunday", "tuesday", "thursday", "alpha", "omega", "member"
]

def _is_protocol_related(text_lower: str) -> bool:
    return any(term in text_lower for term in PROTOCOL_TERMS)

def _build_scenario_answer(question: str, scored_topics):
    text_lower = question.lower()
    day = "Sunday" if "sunday" in text_lower else "Tuesday" if "tuesday" in text_lower else "Thursday" if "thursday" in text_lower else "this service"

    issue = "general"
    if any(k in text_lower for k in ["late", "delay", "delayed"]):
        issue = "late"
    elif any(k in text_lower for k in ["absent", "missing", "didn't show", "no show"]):
        issue = "absent"
    elif any(k in text_lower for k in ["seat", "seating", "chair"]):
        issue = "seating"
    elif any(k in text_lower for k in ["tag", "tags", "lost tag"]):
        issue = "tags"
    elif any(k in text_lower for k in ["count mismatch", "wrong count", "incorrect count"]):
        issue = "count"

    primary_role = "Provost"
    if scored_topics:
        primary_role = PROTOCOL_INFO[scored_topics[0][1]]["title"]

    plans = {
        "late": [
            "Reassign the role immediately to the next available trained member so service flow is not blocked.",
            "Mark the original member as late in duty tracking with exact arrival time.",
            "Brief the late member after service and set early-reporting expectation for next service.",
        ],
        "absent": [
            "Activate replacement immediately from members already present and eligible for the role.",
            "Update attendance and duty table to reflect actual person who served.",
            "Escalate to the Provost after service and document reason in challenges/incidents.",
        ],
        "seating": [
            "Prioritize reserved hospitality seats first, especially Gentleness 03 for executives.",
            "Coordinate quickly with ushers to stop reassignment of protocol-reserved rows.",
            "Record the conflict and agreed escalation path to prevent recurrence next service.",
        ],
        "tags": [
            "Issue tags only to verified serving members and reconcile count before service starts.",
            "If a tag is missing, log holder name/position and begin immediate recovery after service.",
            "Close service with full tag collection and final reconciliation to the provost.",
        ],
        "count": [
            "Recount with two counters (male/female split) and compare both sheets before submission.",
            "Use one final confirmed total for report entry to avoid conflicting records.",
            "Document source of mismatch and prevention step for next service.",
        ],
        "general": [
            "Stabilize service flow first: confirm each core role is covered (Entrance, Tag, Counting, Collection).",
            "Handle exceptions immediately through the Provost instead of waiting until after service.",
            "Capture what happened in report details so operational fixes are repeatable.",
        ],
    }

    steps = "\n".join([f"{idx + 1}. {step}" for idx, step in enumerate(plans[issue])])
    return (
        f"Understood. For **{day}**, handle this through **{primary_role}** with this practical plan:\n\n"
        f"{steps}\n\n"
        "If you want, I can turn this into a short message you can send directly to your protocol team now."
    )

def _build_contextual_kb_answer(question: str, last_topic: str = None):
    """
    Build a useful knowledge-based answer even when AI is unavailable.
    Returns (answer_text, matched_topic_key_or_none).
    """
    text_lower = question.lower().strip()

    # Follow-up handling first
    is_follow_up = any(kw in text_lower for kw in FOLLOW_UP_KEYWORDS)
    if is_follow_up and last_topic and last_topic in PROTOCOL_INFO:
        topic = PROTOCOL_INFO[last_topic]
        return f"**{topic['title']}**: {topic['more']}", last_topic

    # Score each topic by keyword hits
    scored = []
    for key, data in PROTOCOL_INFO.items():
        score = sum(1 for kw in data["keywords"] if kw in text_lower)
        if score > 0:
            scored.append((score, key))

    if scored:
        scored.sort(reverse=True)
        best_key = scored[0][1]
        best = PROTOCOL_INFO[best_key]
        # Question-specific: only the matched role, no extra related topics
        answer = f"**{best['title']}**: {best['info']}"
        return answer, best_key

    # No explicit keyword hit: if protocol-related, still answer in a scenario-based way.
    if _is_protocol_related(text_lower):
        return _build_scenario_answer(question, scored), None

    # Non-protocol fallback.
    return "I can't provide an answer to that question, please ask me protocol related questions.", None

async def answer_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only answer free-text questions in private chats (groups: commands only).
    if update.effective_chat and update.effective_chat.type != "private":
        return

    text = update.message.text

    # 1) Protocol sub-unit document (highest priority)
    doc_answer = search_protocol_document(text)
    if doc_answer:
        await update.message.reply_text(doc_answer)
        return

    # 2) Built-in protocol keyword knowledge
    last_topic = context.user_data.get("last_topic")
    kb_answer, matched_key = _build_contextual_kb_answer(text, last_topic)
    if matched_key:
        context.user_data["last_topic"] = matched_key
    if kb_answer and not kb_answer.startswith("I can't provide an answer"):
        await update.message.reply_text(kb_answer, parse_mode="Markdown")
        return

    # 3) AI (only if document + built-in KB did not answer)
    chat_history = context.user_data.get("ai_chat_history", [])
    ai_response = await get_ai_response(text, chat_history)
    if ai_response:
        chat_history.append({"role": "user", "parts": [text]})
        chat_history.append({"role": "model", "parts": [ai_response]})
        context.user_data["ai_chat_history"] = chat_history[-10:]
        await update.message.reply_text(ai_response)
        return

    if GEMINI_API_KEY:
        logger.error("AI unavailable; using final KB fallback.")

    await update.message.reply_text(kb_answer, parse_mode="Markdown")

async def ai_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current AI availability and cooldown state."""
    now = time.time()
    in_cooldown = AI_DISABLED_UNTIL and now < AI_DISABLED_UNTIL
    remaining = int(AI_DISABLED_UNTIL - now) if in_cooldown else 0

    if not GEMINI_API_KEY:
        message = (
            "AI Status: OFFLINE\n"
            "Reason: GEMINI_API_KEY is not configured."
        )
        await update.message.reply_text(message)
        return

    if not AI_AVAILABLE:
        message = (
            "AI Status: OFFLINE\n"
            "Reason: Gemini client could not initialize with current key."
        )
        await update.message.reply_text(message)
        return

    model_order = AVAILABLE_MODELS[:] if AVAILABLE_MODELS else MODEL_CANDIDATES[:]
    model_preview = ", ".join(model_order[:5]) if model_order else "none detected"

    if in_cooldown:
        message = (
            f"AI Status: COOLDOWN\n"
            f"Retry in: ~{remaining}s\n"
            f"Models: {model_preview}"
        )
    else:
        message = (
            "AI Status: LIVE\n"
            f"Models: {model_preview}"
        )

    await update.message.reply_text(message)
