"""The answer writer: Gemini sees the request and the retrieved documents only, and replies in JSON naming one song,
why, and the text it relied on. temperature 0. With no GEMINI_API_KEY the call is skipped (nothing is sent anywhere)."""
import os
from pathlib import Path
from typing import Dict, List

MODEL = "gemini-3.5-flash-lite"      # the same model that drafts descriptions; bughound's flash-lite-latest alias returned 404 on Nov 17, 2026
ROOT = Path(__file__).resolve().parent.parent
SYSTEM_PROMPT = (
    "You match a listener's request to a song. You are given the request and a few retrieved documents, each tagged "
    "with a song_id. Use only those documents: do not use anything you know about the songs. Choose the one song "
    "that best fits the request. Reply with a JSON object with exactly these keys: "
    '"song_id" (one of the song_ids shown), "reason" (one or two sentences on why it fits, based on the documents), '
    'and "cited_text" (a short passage copied exactly, word for word, from a document of that song).'
)


def get_api_key() -> str:
    """The Gemini key from the environment, or from .env if present. Empty string when there is none."""
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    return os.getenv("GEMINI_API_KEY", "").strip()


def build_prompt(request: str, hits: List[Dict]) -> str:
    """The user message: the request, then each retrieved document with its song_id, title and kind. Nothing else."""
    parts = [f"Request: {request}", "", "Retrieved documents:"]
    for hit in hits:
        parts.append(f"\n[song_id: {hit['song_id']} | title: {hit['title']} | kind: {hit['kind']}]\n{hit['text']}")
    return "\n".join(parts)


def _call_gemini(api_key: str, prompt: str) -> str:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL, contents=prompt,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, temperature=0,
                                           response_mime_type="application/json"))
    return response.text or ""


def ask_gemini(request: str, hits: List[Dict]) -> Dict:
    """Returns {"raw": the reply text or None, "status": what happened}. Never raises: a failed call has raw None."""
    api_key = get_api_key()
    if not api_key:
        return {"raw": None, "status": "no key: call skipped"}
    try:
        return {"raw": _call_gemini(api_key, build_prompt(request, hits)), "status": "ok"}
    except Exception as err:                      # network, quota, bad key: the checker then falls back to the top match
        return {"raw": None, "status": f"call failed: {type(err).__name__}"}
