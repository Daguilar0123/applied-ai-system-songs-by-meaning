"""The --search command: search by meaning, let Gemini name the song, check its reply, print the answer and a short
trace table, and append one JSON line to logs/search_trace.jsonl (the same record, for reading later)."""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    from src.answer import ask_gemini
    from src.checker import check_answer
    from src.song_search import MAX_REQUEST_CHARS, NOTHING_CLOSE, nothing_close, search
except ImportError:  # running as `python src/main.py`
    from answer import ask_gemini
    from checker import check_answer
    from song_search import MAX_REQUEST_CHARS, NOTHING_CLOSE, nothing_close, search

TRACE_PATH = Path(__file__).resolve().parent.parent / "logs" / "search_trace.jsonl"
SHORT = 90          # characters of Gemini's reply shown in the table (the log line keeps up to 400)


def _shorten(text: Optional[str], width: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= width else text[: width - 3] + "..."


def _answer_block(result: Dict, hits: List[Dict]) -> List[str]:
    score = next((h["score"] for h in hits if h["song_id"] == result["song_id"]), None)
    label = "Answer (fallback: top match, no checked Gemini answer)" if result["fallback"] else "Answer"
    return [f"{label}: {result['title']}" + (f" (score {score:.2f})" if score is not None else ""),
            f"Why: {result['reason']}",
            f"From the text: \"{_shorten(result['cited_text'], 300)}\""]


def _trace_table(record: Dict) -> List[str]:
    rows = ["--- trace ---", f"request   : {_shorten(record['request'], 100)}"]
    if record["top3"]:
        for n, hit in enumerate(record["top3"], start=1):
            rows.append(f"{'top 3' if n == 1 else '':<10}: {n}. {hit['title']} ({hit['kind']})  {hit['score']:.3f}")
    else:
        rows.append("top 3     : (none)")
    reply = _shorten(record["gemini_reply"], SHORT) if record["gemini_reply"] else f"({record['gemini_status']})"
    rows += [f"gemini    : {reply}", f"check     : {record['check']}", f"decision  : {record['decision']}"]
    return rows


def run_search(request: str, kind: Optional[str] = None, k: int = 3, trace_path: Optional[Path] = None) -> str:
    """Run one search end to end. Returns the text to print; writes one trace line as a side effect."""
    length = len(request.strip())
    hits = [] if length > MAX_REQUEST_CHARS else search(request, k=k, kind=kind)
    reply = {"raw": None, "status": "not called"}
    result: Optional[Dict] = None
    if length > MAX_REQUEST_CHARS:
        check, decision = "skipped", "request too long"
        body = [f"Request too long: {length} characters, and the limit is {MAX_REQUEST_CHARS}. "
                "Shorten it to the main idea and try again."]
    elif not request.strip():
        check, decision, body = "skipped", "empty request", ["The request is empty: type what the song is about."]
    elif nothing_close(hits):
        detail = f" The best match scored {hits[0]['score']:.2f}, below the line." if hits else ""
        check, decision, body = "skipped", NOTHING_CLOSE, [NOTHING_CLOSE.capitalize() + "." + detail]
    else:
        reply = ask_gemini(request, hits)
        result = check_answer(reply["raw"], hits)
        if result["fallback"]:
            check = f"{'skipped' if reply['raw'] is None else 'rejected'} ({result['problem']})"
            decision = "fallback: top match"
        else:
            check, decision = "pass", "checked Gemini answer"
        body = _answer_block(result, hits)

    record = {"time": datetime.now().isoformat(timespec="seconds"), "request": request, "kind": kind,
              "top3": [{"song_id": h["song_id"], "title": h["title"], "kind": h["kind"], "score": h["score"]} for h in hits[:3]],
              "gemini_status": reply["status"], "gemini_reply": _shorten(reply["raw"], 400) if reply["raw"] else None,
              "check": check, "decision": decision,
              "answer": ({"song_id": result["song_id"], "title": result["title"], "reason": result["reason"],
                          "cited_text": result["cited_text"], "fallback": result["fallback"]} if result else None)}
    path = Path(trace_path) if trace_path else TRACE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as log:
        log.write(json.dumps(record, ensure_ascii=False) + "\n")
    return "\n".join(body + [""] + _trace_table(record) + [f"logged to : {path.name}"])
