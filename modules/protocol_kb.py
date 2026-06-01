"""Load and search the About Protocol Sub-Unit knowledge document."""
import logging
import os
import re
from functools import lru_cache

logger = logging.getLogger(__name__)

PDF_FILENAMES = [
    "About Protocol Sub-Unit (Hospitality Unit).pdf",
    "about-protocol sub-unit.pdf",
    "about-protocol.pdf",
]

STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "what", "how", "when",
    "do", "does", "did", "i", "to", "for", "of", "in", "on", "at", "and",
    "or", "it", "this", "that", "my", "me", "can", "you", "your", "be",
    "role", "duty", "duties", "responsibility", "responsibilities",
}

# Role sections in the PDF (order matters for parsing)
ROLE_DEFINITIONS = [
    {
        "key": "provost",
        "title": "Provost",
        "aliases": ["provost", "supervisor", "supervise"],
        "start_patterns": [
            r"1\.\s*Provost\s*:",
            r"\bProvost\s*:",
        ],
    },
    {
        "key": "entrance",
        "title": "Entrance Allocation",
        "aliases": ["entrance", "entrance allocation", "allocate", "allocation", "seat", "seating"],
        "start_patterns": [
            r"2\.\s*Entrance\s+Allocation\s*:",
            r"\bEntrance\s+Allocation\s*:",
        ],
    },
    {
        "key": "tag_allocation",
        "title": "Tag Allocation",
        "aliases": ["tag allocation", "allocate tag", "giving tags", "tags before"],
        "start_patterns": [
            r"3\.\s*Tag\s+Allocation\s*:",
            r"\bTag\s+Allocation\s*:",
        ],
    },
    {
        "key": "counting",
        "title": "Counting during pre-service",
        "aliases": ["counting", "count", "counter", "male", "female", "pre-service count"],
        "start_patterns": [
            r"4\.\s*Counting\s+during\s+pre\s*-\s*service\s*:",
            r"\bCounting\s+during\s+pre\s*-\s*service\s*:",
            r"\bCounting\s+during\s+pre-service\s*:",
        ],
    },
    {
        "key": "tag_collection",
        "title": "Tag Collection",
        "aliases": ["tag collection", "collect tags", "collecting tags", "collection", "return tags"],
        "start_patterns": [
            r"5\.\s*Tag\s+Collection\s*:",
            r"\bTag\s+Collection\s*:",
        ],
    },
]


def _find_pdf_path():
    root = os.path.dirname(os.path.dirname(__file__))
    for name in PDF_FILENAMES:
        path = os.path.join(root, name)
        if os.path.exists(path):
            return path
    return None


@lru_cache(maxsize=1)
def load_protocol_document_text():
    pdf_path = _find_pdf_path()
    if not pdf_path:
        logger.warning("Protocol knowledge PDF not found in project root.")
        return ""

    try:
        from pypdf import PdfReader

        reader = PdfReader(pdf_path)
        parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                parts.append(text.strip())
        full_text = "\n\n".join(parts)
        logger.info(
            "Loaded protocol KB from %s (%s chars)",
            os.path.basename(pdf_path),
            len(full_text),
        )
        return full_text
    except Exception as exc:
        logger.error("Failed to read protocol PDF: %s", exc)
        return ""


@lru_cache(maxsize=1)
def _parse_role_sections():
    """Split PDF text into one block per protocol role."""
    doc_text = load_protocol_document_text()
    if not doc_text:
        return {}

    sections = {}
    for role in ROLE_DEFINITIONS:
        start_pos = None
        for pattern in role["start_patterns"]:
            match = re.search(pattern, doc_text, re.IGNORECASE)
            if match:
                start_pos = match.start()
                break
        if start_pos is None:
            continue

        # End at the next numbered role heading (e.g. "2. Entrance...")
        next_role = re.search(
            r"\n\s*\d+\.\s+[A-Za-z]",
            doc_text[start_pos + 5 :],
        )
        if next_role:
            end_pos = start_pos + 5 + next_role.start()
            body = doc_text[start_pos:end_pos].strip()
        else:
            body = doc_text[start_pos:].strip()

        # Clean: remove leading "1. Provost:" numbering, keep "Provost: ..."
        body = re.sub(
            r"^\d+\.\s*",
            "",
            body,
            count=1,
        )
        body = re.sub(r"\s+", " ", body).strip()
        body = _strip_duplicate_title_prefix(role["title"], body)
        sections[role["key"]] = {"title": role["title"], "body": body}

    return sections


def _question_terms(question: str):
    words = re.findall(r"[a-zA-Z0-9]+", question.lower())
    return {w for w in words if len(w) > 2 and w not in STOP_WORDS}


def _detect_role_from_question(question: str):
    """Pick the single best-matching role for a question."""
    q_lower = question.lower()
    terms = _question_terms(question)

    best_key = None
    best_score = 0

    for role in ROLE_DEFINITIONS:
        score = 0
        for alias in role["aliases"]:
            if alias in q_lower:
                score += len(alias.split()) + 2

        for alias in role["aliases"]:
            for word in alias.split():
                if word in terms:
                    score += 1

        if role["key"] in q_lower.replace(" ", "_"):
            score += 3

        if score > best_score:
            best_score = score
            best_key = role["key"]

    # Require a clear role signal (avoid defaulting on generic questions)
    if best_score < 2:
        return None
    return best_key


def _normalize_label(text: str) -> str:
    return re.sub(r"[\s\-–]+", "", text.lower())


def _strip_duplicate_title_prefix(title: str, body: str) -> str:
    """Remove repeated role label at start of body from PDF line breaks."""
    body = body.strip()
    colon_idx = body.find(":")
    if colon_idx == -1 or colon_idx > 80:
        return body
    prefix = body[:colon_idx]
    if _normalize_label(prefix) in _normalize_label(title) or _normalize_label(title) in _normalize_label(prefix):
        return body[colon_idx + 1 :].strip()
    return body


def _format_role_answer(title: str, body: str) -> str:
    """Format as 'Title: body' matching the document style."""
    body = _strip_duplicate_title_prefix(title, body.strip())
    if body.lower().startswith(title.lower() + ":"):
        return body
    return f"{title}: {body}"


def search_protocol_document(question: str, max_chunks: int = 1):
    """
    Return a question-specific answer from the protocol PDF.
    Prefer exactly one role section when the question targets a role.
    """
    _ = max_chunks  # kept for API compatibility; answers are always focused
    sections = _parse_role_sections()
    if not sections:
        return None

    role_key = _detect_role_from_question(question)
    if role_key and role_key in sections:
        sec = sections[role_key]
        return _format_role_answer(sec["title"], sec["body"])

    # No specific role: search short topical paragraphs (not the full roles list)
    doc_text = load_protocol_document_text()
    terms = _question_terms(question)
    if not terms:
        return None

    # Exclude the big numbered roles block from generic search
    roles_block_start = re.search(
        r"Roles\s+and\s+Responsibilities",
        doc_text,
        re.IGNORECASE,
    )
    generic_text = doc_text
    if roles_block_start:
        generic_text = (
            doc_text[: roles_block_start.start()]
            + "\n\n"
            + doc_text[roles_block_start.start() + 2000 :]
        )

    paragraphs = [
        p.strip()
        for p in re.split(r"\n\s*\n+", generic_text)
        if len(p.strip()) >= 40
    ]

    scored = []
    for para in paragraphs:
        if re.match(r"^\d+\.\s+\w+", para):
            continue
        para_lower = para.lower()
        score = sum(1 for term in terms if term in para_lower)
        if score > 0:
            scored.append((score, para))

    if not scored:
        return None

    scored.sort(key=lambda x: (-x[0], len(x[1])))
    best = scored[0][1]
    best = re.sub(r"\s+", " ", best).strip()
    if len(best) > 3800:
        best = best[:3800].rstrip() + "..."
    return best
