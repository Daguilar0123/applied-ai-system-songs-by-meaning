"""The checker: Gemini's reply must be valid JSON, an object, with song_id / reason / cited_text, naming a song that was
actually retrieved and citing text that is really in that song's retrieved document. Anything else is rejected, and so is
no reply at all; in both cases the answer is built from the top hit and its text and marked fallback."""
import json
import re
from typing import Dict, List, Optional

FIELDS = ("song_id", "reason", "cited_text")
MIN_CITED_WORDS = 3     # a one-letter "quote" is always somewhere in the text; require a real passage
FALLBACK_REASON = "Closest match by meaning; no checked Gemini answer was available."


def _normal(text: str) -> str:
    """Lowercase and collapse whitespace, so line breaks and capitalization do not decide a quote check."""
    return re.sub(r"\s+", " ", text).strip().lower()


def _problem(raw: Optional[str], hits: List[Dict]) -> Optional[str]:
    """Why the reply is rejected, or None when it passes."""
    if raw is None:
        return "no Gemini reply (no key, or the call failed)"
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return "reply is not valid JSON"
    if not isinstance(data, dict):
        return "reply is not a JSON object"
    for field in FIELDS:
        if not isinstance(data.get(field), str) or not data[field].strip():
            return f"reply lacks a usable '{field}'"
    documents = [h["text"] for h in hits if h["song_id"] == data["song_id"]]
    if not documents:
        return f"song_id '{data['song_id']}' is not among the retrieved songs"
    cited = _normal(data["cited_text"])
    if len(cited.split()) < MIN_CITED_WORDS:
        return f"cited_text is shorter than {MIN_CITED_WORDS} words"
    if not any(cited in _normal(doc) for doc in documents):
        return "cited_text was not found in that song's retrieved document"
    return None


def check_answer(raw: Optional[str], hits: List[Dict]) -> Dict:
    """Result: song_id, title, reason, cited_text, fallback (bool), problem (why it fell back, else None)."""
    problem = _problem(raw, hits) if hits else "no documents were retrieved"
    if problem is None:
        data = json.loads(raw)
        title = next(h["title"] for h in hits if h["song_id"] == data["song_id"])
        return {"song_id": data["song_id"], "title": title, "reason": data["reason"].strip(),
                "cited_text": data["cited_text"].strip(), "fallback": False, "problem": None}
    if not hits:
        return {"song_id": None, "title": None, "reason": None, "cited_text": None, "fallback": True, "problem": problem}
    top = hits[0]
    return {"song_id": top["song_id"], "title": top["title"], "reason": FALLBACK_REASON,
            "cited_text": top["text"], "fallback": True, "problem": problem}
