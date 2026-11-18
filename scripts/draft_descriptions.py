"""Draft song descriptions: Wikipedia text in, a short Gemini description out, saved as "not approved".

    .venv/bin/python scripts/draft_descriptions.py --dry-run     # fetch only; print what Gemini would be sent
    .venv/bin/python scripts/draft_descriptions.py               # the 5 starter songs (needs GEMINI_API_KEY)
    .venv/bin/python scripts/draft_descriptions.py --all         # all 9 songs from the prompt's list
    .venv/bin/python scripts/draft_descriptions.py --only fast-car --force   # redo one unapproved draft

Writes data/library/descriptions.json. A record with "approved": true is never overwritten. Danny edits
"description" by hand and flips "approved"; "draft" keeps Gemini's original so the edit is visible later.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

try:
    from scripts.library_catalog import MODERN, STARTER_IDS
except ImportError:  # running as `python scripts/draft_descriptions.py`
    from library_catalog import MODERN, STARTER_IDS

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "library" / "descriptions.json"
USER_AGENT = "songsearch-build/0.1 (https://github.com/Daguilar0123/applied-ai-system-songs-by-meaning) urllib"
MODEL = "gemini-3.5-flash-lite"           # bughound's "gemini-flash-lite-latest" returned 404 on Nov 17, 2026; this is the newest flash-lite the key lists
SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
EXTRACT_URL = ("https://en.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1"
               "&format=json&formatversion=2&titles={title}")
GUARD_PHRASES = ("batman smells",)        # a line of the 1960s parody: it must never reach a stored description
SYSTEM_PROMPT = (
    "You write short descriptions of songs for a search index. Use only the article text you are given; if it does "
    "not say what the song is about, say only what it does support. Write 2 to 4 sentences of plain prose about "
    "what the song is about: its subject, story, feeling and who or what it addresses, then who made it. Do not "
    "quote lyrics, do not put lyric phrases in quotation marks, and do not describe the music or chart "
    "performance beyond one clause."
)


# ---------- pure helpers (tested without a network) ----------

def extract_sections(full_text: str, names) -> str:
    """Return the body of each named `== Heading ==` section, subsections included, joined by blank lines."""
    heading = re.compile(r"^(=+)\s*(.+?)\s*=+\s*$", re.M)
    marks = [(m.start(), m.end(), len(m.group(1)), m.group(2)) for m in heading.finditer(full_text)]
    wanted = {n.lower() for n in names}
    parts = []
    for i, (_, end, level, title) in enumerate(marks):
        if title.lower() not in wanted:
            continue
        stop = len(full_text)
        for later in marks[i + 1:]:
            if later[2] <= level:          # next heading of the same or a higher level ends the section
                stop = later[0]
                break
        parts.append(full_text[end:stop].strip())
    return "\n\n".join(p for p in parts if p)


def build_source_text(article: Dict, entry: Dict) -> str:
    """The text sent to Gemini: the summary (unless the entry leaves it out) plus the entry's named sections."""
    pieces = []
    if entry.get("use_summary", True) and article.get("summary"):
        pieces.append(article["summary"].strip())
    sections = extract_sections(article.get("full_text", ""), entry.get("sections") or ())
    if entry.get("max_paragraphs"):
        sections = "\n".join(sections.split("\n")[:entry["max_paragraphs"]])
    if sections:
        pieces.append(sections)
    return "\n\n".join(pieces)


def violates_guard(text: str) -> bool:
    """True when a draft contains a line of the Batman parody (the lines are never stored)."""
    lowered = text.lower()
    return any(phrase in lowered for phrase in GUARD_PHRASES)


def merge_record(existing: Optional[Dict], new: Dict, force: bool = False) -> Dict:
    """Pick the record to keep. Approved records always win; an unapproved one is replaced only with --force."""
    if existing is None:
        return new
    if existing.get("approved"):
        return existing
    return new if force else existing


# ---------- network ----------

def _get_json(url: str) -> Dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def fetch_article(wiki_title: str) -> Dict:
    """Wikipedia summary (url, revision id, intro) plus the full plain text for section lookups."""
    quoted = urllib.parse.quote(wiki_title.replace(" ", "_"), safe="()")
    summary = _get_json(SUMMARY_URL.format(title=quoted))
    full = _get_json(EXTRACT_URL.format(title=urllib.parse.quote(wiki_title.replace(" ", "_"), safe="")))
    return {
        "url": summary["content_urls"]["desktop"]["page"],
        "revision_id": int(summary["revision"]),
        "summary": summary.get("extract", ""),
        "full_text": full["query"]["pages"][0].get("extract", ""),
    }


def draft_with_gemini(source_text: str, entry: Dict) -> Dict:
    """One Gemini call, temperature 0. Returns {"text", "model_version"}."""
    from dotenv import load_dotenv
    from google import genai
    from google.genai import types
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set. Put it in .env (see .env.example) or use --dry-run.")
    client = genai.Client(api_key=api_key)
    prompt = f"Song: {entry['title']}" + (f" by {entry['artist']}" if entry.get("artist") else "")
    prompt += f"\n{entry.get('extra', '')}\n\nArticle text:\n{source_text}"
    response = client.models.generate_content(
        model=MODEL, contents=prompt,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, temperature=0))
    return {"text": " ".join((response.text or "").split()), "model_version": getattr(response, "model_version", None)}


# ---------- command line ----------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Draft song descriptions from Wikipedia with Gemini.")
    parser.add_argument("--all", action="store_true", help="all 9 songs, not just the 5 starters")
    parser.add_argument("--only", metavar="ID", help="one song id, e.g. fast-car")
    parser.add_argument("--force", action="store_true", help="redraft unapproved records (approved ones are never touched)")
    parser.add_argument("--dry-run", action="store_true", help="fetch Wikipedia and print what Gemini would be sent; call nothing, write nothing")
    args = parser.parse_args(argv)

    wanted = [e for e in MODERN if (args.only == e["id"] if args.only else (args.all or e["id"] in STARTER_IDS))]
    if not wanted:
        parser.error(f"no song matches --only {args.only!r}; ids: {', '.join(e['id'] for e in MODERN)}")

    existing = {r["id"]: r for r in json.loads(OUT_PATH.read_text(encoding="utf-8"))} if OUT_PATH.exists() else {}
    records = dict(existing)
    for entry in wanted:
        old = existing.get(entry["id"])
        if old and (old.get("approved") or not args.force) and not args.dry_run:
            print(f"- {entry['id']}: kept the existing {'approved' if old.get('approved') else 'draft'} record")
            continue
        try:
            article = fetch_article(entry["wiki_title"])
        except (urllib.error.URLError, KeyError, ValueError) as err:
            print(f"- {entry['id']}: Wikipedia fetch failed ({type(err).__name__}: {err}); skipped", file=sys.stderr)
            continue
        source_text = build_source_text(article, entry)
        if args.dry_run:
            print(f"\n=== {entry['id']}  rev {article['revision_id']}  {article['url']}  ({len(source_text)} chars to Gemini) ===")
            print(source_text)
            time.sleep(1)
            continue
        if not source_text.strip():
            print(f"- {entry['id']}: no article text found for the chosen sections; skipped", file=sys.stderr)
            continue
        try:
            result = draft_with_gemini(source_text, entry)
        except RuntimeError as err:          # no key: stop cleanly instead of a traceback
            print(f"Stopped: {err}", file=sys.stderr)
            return 1
        if not result["text"] or violates_guard(result["text"]):
            print(f"- {entry['id']}: draft empty or contained a parody line; not saved", file=sys.stderr)
            continue
        new = {"id": entry["id"], "title": entry["title"], "artist": entry["artist"], "year": entry["year"],
               "wikipedia_url": article["url"], "revision_id": article["revision_id"],
               "description": result["text"], "draft": result["text"],
               "drafted_by": MODEL, "model_version": result["model_version"], "drafted_on": date.today().isoformat(),
               "approved": False}
        records[entry["id"]] = merge_record(old, new, args.force)
        print(f"- {entry['id']}: drafted ({len(result['text'])} chars), approved=false")
        time.sleep(1)                       # be polite to Wikipedia

    if not args.dry_run:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ordered = [records[e["id"]] for e in MODERN if e["id"] in records]
        OUT_PATH.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {len(ordered)} records to {OUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
