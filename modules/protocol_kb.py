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
}


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
        logger.info("Loaded protocol KB from %s (%s chars)", os.path.basename(pdf_path), len(full_text))
        return full_text
    except Exception as exc:
        logger.error("Failed to read protocol PDF: %s", exc)
        return ""


def _question_terms(question: str):
    words = re.findall(r"[a-zA-Z0-9]+", question.lower())
    return {w for w in words if len(w) > 2 and w not in STOP_WORDS}


def _split_chunks(text: str, min_len: int = 60):
    chunks = re.split(r"\n\s*\n+", text)
    cleaned = [c.strip() for c in chunks if len(c.strip()) >= min_len]
    if cleaned:
        return cleaned
    return [text.strip()] if text.strip() else []


def search_protocol_document(question: str, max_chunks: int = 2):
    """
    Search the protocol PDF for the best matching passage(s).
    Returns answer text or None if no useful match.
    """
    doc_text = load_protocol_document_text()
    if not doc_text:
        return None

    terms = _question_terms(question)
    if not terms:
        return None

    chunks = _split_chunks(doc_text)
    scored = []

    for chunk in chunks:
        chunk_lower = chunk.lower()
        score = sum(1 for term in terms if term in chunk_lower)
        if score > 0:
            scored.append((score, chunk))

    if not scored:
        return None

    scored.sort(key=lambda x: (-x[0], -len(x[1])))
    top_score = scored[0][0]
    # Require at least one meaningful term hit (or strong multi-hit)
    if top_score < 1:
        return None

    selected = [chunk for score, chunk in scored[:max_chunks] if score >= max(1, top_score - 1)]
    answer = "\n\n".join(selected)
    if len(answer) > 3800:
        answer = answer[:3800].rstrip() + "..."
    return answer
