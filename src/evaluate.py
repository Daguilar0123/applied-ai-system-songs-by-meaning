"""Evaluation script: run the golden set (evals/golden_set.json) against the system as it is and report what happens.

    .venv/bin/python -m src.evaluate                 # no Gemini calls, even if a key exists (repeatable offline run)
    .venv/bin/python -m src.evaluate --with-gemini   # uses the key in the environment or .env; writes results_with_gemini.md

It uses the search code as it is (src.song_search, src.search_cli.run_search, src.checker) and changes none of it. Nothing
here tunes MIN_SCORE or the requests: a failing row is a result. Prints the summary and writes the same Markdown to
evals/results.md. Exits 0 whenever it ran to the end.
"""
import argparse
import json
import re
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src import search_cli
from src.answer import get_api_key
from src.checker import check_answer
from src.song_search import MIN_SCORE, VECTORS_PATH, keyword_search, search
from src.song_search import _words as matcher_words   # the word matcher's own tokenizer and stop list, read only

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PATH = ROOT / "evals" / "golden_set.json"
RESULTS_PATH = ROOT / "evals" / "results.md"
RESULTS_GEMINI_PATH = ROOT / "evals" / "results_with_gemini.md"
TRACE_MARK = "--- trace ---"

# Common words that do not count as "important" when checking what a request shares with a song's text. Written
# for this script on purpose, not borrowed from the search code, so the check stays independent of it.
STOP_WORDS = frozenset("""a about above after again all also am an and any are as at be because been before being below between both
but by can could did do does doing down during each few for from further had has have having he her here hers him his how i if
in into is it its itself just me more most my no nor not now of off on once only or other our out over own same she should so
some such than that the their them then there these they this those through to too under until up very was we were what when
where which while who whom why will with would you your yours rather""".split())


def load_golden() -> Dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in STOP_WORDS}


def shared_words(request: str, text: str) -> List[str]:
    """Words the request and the text have in common after lowercasing and dropping stop words, sorted."""
    return sorted(_words(request) & _words(text))


def hit_rate(rows: List[Dict], field: str, shares_important_word: bool, approved_only: bool = True) -> Tuple[int, int]:
    """(hits, total) of `field` over the retrieval rows in one group. Unapproved rows are left out unless approved_only is False."""
    group = [r for r in rows if r["shares_important_word"] == shares_important_word and (r["approved"] or not approved_only)]
    return sum(bool(r[field]) for r in group), len(group)


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _stored_texts() -> Dict[str, List[str]]:
    """Every stored document text per song id, read from the saved vectors file."""
    by_song: Dict[str, List[str]] = {}
    for doc in json.loads(VECTORS_PATH.read_text(encoding="utf-8"))["documents"]:
        by_song.setdefault(doc["song_id"], []).append(doc["text"])
    return by_song


def run_final(request: str, work_dir: Path) -> Dict:
    """The function --search calls, with its trace line going to a scratch file instead of logs/. Returns the trace record
    (decision, top3, answer ...) plus "answer_text", the printed answer without the trace table."""
    trace = work_dir / "trace.jsonl"
    text = search_cli.run_search(request, trace_path=trace)
    record = json.loads(trace.read_text(encoding="utf-8").splitlines()[-1])
    record["answer_text"] = text.split(TRACE_MARK)[0].strip()
    return record


def _fmt_hits(hits: List[Dict], digits: int) -> str:
    return "<br>".join(f"{n}. {h['song_id']} ({h['score']:.{digits}f})" for n, h in enumerate(hits, 1)) or "(no matches)"


def _yn(flag: bool) -> str:
    return "hit" if flag else "miss"


def evaluate(with_gemini: bool = False) -> Tuple[str, Dict]:
    """Run everything. Returns (markdown, summary numbers)."""
    golden = load_golden()
    k = golden["k"]
    items = golden["items"]
    stored = _stored_texts()
    key_present = bool(get_api_key())
    real_ask = search_cli.ask_gemini
    if not (with_gemini and key_present):
        search_cli.ask_gemini = lambda request, hits: {"raw": None, "status": "no Gemini call in this run"}
    used_gemini = with_gemini and key_present

    out: List[str] = []
    rows: List[Dict] = []
    guard_rows: List[Dict] = []
    flagged: List[str] = []
    finals: Dict[str, Dict] = {}
    repeats: List[Tuple[str, bool]] = []
    quotes: List[Tuple[str, bool]] = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            # ---- retrieval items ----
            for item in (i for i in items if i["type"] == "retrieval"):
                wanted = set(item["hit_song_ids"])
                word_hits, meaning_hits = keyword_search(item["request"], k=k), search(item["request"], k=k)
                row = {"id": item["id"], "approved": item["approved_by_danny"],
                       "shares_important_word": item["shares_important_word_with_lyric"],
                       "word_hit3": any(h["song_id"] in wanted for h in word_hits),
                       "word_hit1": bool(word_hits) and word_hits[0]["song_id"] in wanted,
                       "meaning_hit3": any(h["song_id"] in wanted for h in meaning_hits),
                       "meaning_hit1": bool(meaning_hits) and meaning_hits[0]["song_id"] in wanted,
                       "top_score": meaning_hits[0]["score"] if meaning_hits else 0.0}
                rows.append(row)
                shared = sorted({w for song in wanted for text in stored.get(song, []) for w in shared_words(item["request"], text)})
                if not item["shares_important_word_with_lyric"] and shared:
                    flagged.append(f"{item['id']}: labelled as sharing no important word, but shares: {', '.join(shared)}")
                matched = sorted({w for h in word_hits if h["song_id"] in wanted for text in stored.get(h["song_id"], [])
                                  for w in matcher_words(item["request"]) & matcher_words(text)})
                if row["word_hit3"] and not item["shares_important_word_with_lyric"]:
                    flagged.append(f"{item['id']}: word matching counts as a hit, but the label says no important word is shared. "
                                   f"It matched on: {', '.join(matched)} (words this script's stop list drops but the word matcher keeps)")
                label = "approved" if item["approved_by_danny"] else "not yet approved"
                out += [f"### {item['id']}: \"{item['request']}\"", "",
                        f"Expected song: `{', '.join(sorted(wanted))}`. Labelled as sharing an important word with the lyric: "
                        f"{'yes' if item['shares_important_word_with_lyric'] else 'no'}. Approved: {label}.", "",
                        "| method | top 3 (song id, score) | hit in top 3 | hit at rank 1 |", "|---|---|---|---|",
                        f"| word matching | {_fmt_hits(word_hits, 2)} | {_yn(row['word_hit3'])} | {_yn(row['word_hit1'])} |",
                        f"| meaning search | {_fmt_hits(meaning_hits, 3)} | {_yn(row['meaning_hit3'])} | {_yn(row['meaning_hit1'])} |", "",
                        f"Words the word matcher matched on, using its own stop list: {', '.join(matched) if matched else '(none)'}", "",
                        f"Words shared with the expected song's stored text, using this script's stop list: {', '.join(shared) if shared else '(none)'}"
                        + (" **FLAGGED: the label says none**" if (not item["shares_important_word_with_lyric"] and shared) else ""), ""]
            # ---- final answers for every item, twice ----
            for item in items:
                first, second = run_final(item["request"], work), run_final(item["request"], work)
                finals[item["id"]] = first
                if used_gemini:
                    same = (first["answer"] or {}).get("song_id") == (second["answer"] or {}).get("song_id") and first["decision"] == second["decision"]
                else:
                    same = ([(h["song_id"], round(h["score"], 4)) for h in first["top3"]] == [(h["song_id"], round(h["score"], 4)) for h in second["top3"]]
                            and first["decision"] == second["decision"])
                repeats.append((item["id"], same))
                if first["answer"] and first["answer"]["cited_text"]:
                    songs_docs = [_collapse(h["text"]) for h in search(item["request"], k=k) if h["song_id"] == first["answer"]["song_id"]]
                    quotes.append((item["id"], any(_collapse(first["answer"]["cited_text"]) in doc for doc in songs_docs)))
            # ---- guardrail items ----
            for item in (i for i in items if i["type"] == "guardrail"):
                rule, forbidden = item["pass_rule"], [f.lower() for f in item.get("forbidden_in_answer", [])]
                record = finals[item["id"]]
                leaked = [f for f in forbidden if f in record["answer_text"].lower()]
                if rule == "handled_empty":
                    inputs = [item["request"]] + item.get("also_try", [])
                    outcomes = [run_final(text, work) for text in inputs]
                    ok = all(o["answer"] is None and not o["top3"] and o["decision"] == "empty request" for o in outcomes)
                    happened = f"{len(inputs)} inputs, no crash, decisions: {', '.join(o['decision'] for o in outcomes)}; song named: " \
                               f"{'yes' if any(o['answer'] for o in outcomes) else 'no'}"
                    shown = " / ".join(repr(t) for t in inputs)
                elif rule == "no_match":
                    ok = record["decision"] == "nothing close found" and not leaked and record["answer"] is None
                    top = record["top3"][0] if record["top3"] else None
                    happened = f"decision: {record['decision']}; best score {top['score']:.3f} ({top['song_id']}) against MIN_SCORE {MIN_SCORE}" if top else f"decision: {record['decision']}"
                    happened += f"; forbidden text in answer: {', '.join(leaked) or 'none'}"
                    shown = repr(item["request"])
                else:  # injection_resisted
                    retrieved = search(item["request"], k=k)
                    answer = record["answer"]
                    names_retrieved = answer is None or answer["song_id"] in {h["song_id"] for h in retrieved}
                    cited_ok = answer is None or any(_collapse(answer["cited_text"]) in _collapse(h["text"]) for h in retrieved if h["song_id"] == answer["song_id"])
                    ok = names_retrieved and cited_ok and not leaked
                    happened = (f"decision: {record['decision']}; names: {answer['song_id'] if answer else 'nothing'}; "
                                f"song was retrieved: {'yes' if names_retrieved else 'NO'}; cited text found in retrieved document: "
                                f"{'yes' if cited_ok else 'NO'}; forbidden text in answer: {', '.join(leaked) or 'none'}")
                    shown = repr(item["request"])
                guard_rows.append({"id": item["id"], "pass": ok, "approved": item["approved_by_danny"]})
                if not ok:
                    flagged.append(f"{item['id']} ({item['case']}) FAILED: {happened}")
                item["_row"] = f"| {item['id']} ({item['case']}) | {shown} | {item['expected']} | {happened} | {'pass' if ok else '**FAIL**'}" \
                               f"{'' if item['approved_by_danny'] else ' (not yet approved)'} |"
            # ---- checker on bad replies ----
            hits = search("which song says let my people go", k=k)
            top = hits[0]
            quote = " ".join(top["text"].split()[:6])
            replies = [("not JSON", "Sure! It is " + top["song_id"], False),
                       ("JSON that is not an object", json.dumps([top["song_id"]]), False),
                       ("a missing field", json.dumps({"song_id": top["song_id"], "reason": "r"}), False),
                       ("a song id that was not retrieved", json.dumps({"song_id": "bohemian-rhapsody", "reason": "r", "cited_text": quote}), False),
                       ("cited text not in the retrieved document", json.dumps({"song_id": top["song_id"], "reason": "r", "cited_text": "a line that is not in any retrieved verse"}), False),
                       ("a good reply", json.dumps({"song_id": top["song_id"], "reason": "It fits.", "cited_text": quote}), True)]
            checker_rows = []
            for label, raw, should_pass in replies:
                result = check_answer(raw, hits)
                accepted = not result["fallback"]
                checker_rows.append((label, should_pass, accepted, result["problem"]))
    finally:
        search_cli.ask_gemini = real_ask

    # ---- summary numbers ----
    def rate(field, shares):
        return hit_rate(rows, field, shares), hit_rate(rows, field, shares, approved_only=False)
    approved_guard = [g for g in guard_rows if g["approved"]]
    bad_rejected = sum(1 for _, should, accepted, _ in checker_rows if not should and not accepted)
    good_accepted = sum(1 for _, should, accepted, _ in checker_rows if should and accepted)
    hit_scores = [r["top_score"] for r in rows if r["meaning_hit3"] and r["approved"]]
    no_match_scores = [finals[i["id"]]["top3"][0]["score"] for i in items if i["type"] == "guardrail" and i["pass_rule"] == "no_match" and finals[i["id"]]["top3"]]
    approved_ids = {i["id"] for i in items if i["approved_by_danny"]}
    summary = {
        "word_none": rate("word_hit3", False), "meaning_none": rate("meaning_hit3", False),
        "word_ctl": rate("word_hit3", True), "meaning_ctl": rate("meaning_hit3", True),
        "word1_none": rate("word_hit1", False), "meaning1_none": rate("meaning_hit1", False),
        "word1_ctl": rate("word_hit1", True), "meaning1_ctl": rate("meaning_hit1", True),
        "guardrails": (sum(g["pass"] for g in approved_guard), len(approved_guard)),
        "repeats": (sum(s for i, s in repeats if i in approved_ids), sum(1 for i, _ in repeats if i in approved_ids)),
        "quotes": (sum(q for i, q in quotes if i in approved_ids), sum(1 for i, _ in quotes if i in approved_ids)),
        "bad_rejected": bad_rejected, "good_accepted": good_accepted,
        "avg_hit": sum(hit_scores) / len(hit_scores) if hit_scores else None,
        "avg_no_match": sum(no_match_scores) / len(no_match_scores) if no_match_scores else None,
    }

    def line(label, key, plain=False):
        (a, b), (c, d) = summary[key]
        return f"| {label} | {a} of {b} | {c} of {d} |"
    md = [f"# Evaluation results: search by meaning", "",
          f"Run on {date.today().isoformat()} with `python -m src.evaluate{' --with-gemini' if with_gemini else ''}`. "
          f"`MIN_SCORE` = {MIN_SCORE}. Gemini key present: {'yes' if key_present else 'no'}. Gemini used in this run: {'yes' if used_gemini else 'no'}. "
          f"Golden set: {len(items)} items, {len(approved_ids)} approved by Danny. Top 3 are documents (verses or descriptions), so one song can fill two places.", "",
          "## Summary", "",
          "Headline counts use approved items only; the last column counts every item, approved or not.", "",
          "| measure | approved items | all items |", "|---|---|---|",
          line("Requests sharing no important word: word matching, hit in top 3", "word_none"),
          line("Requests sharing no important word: meaning search, hit in top 3", "meaning_none"),
          line("Requests sharing no important word: word matching, hit at rank 1", "word1_none"),
          line("Requests sharing no important word: meaning search, hit at rank 1", "meaning1_none"),
          line("Control requests: word matching, hit in top 3", "word_ctl"),
          line("Control requests: meaning search, hit in top 3", "meaning_ctl"),
          line("Control requests: word matching, hit at rank 1", "word1_ctl"),
          line("Control requests: meaning search, hit at rank 1", "meaning1_ctl"),
          f"| Guardrails passed | {summary['guardrails'][0]} of {summary['guardrails'][1]} | {sum(g['pass'] for g in guard_rows)} of {len(guard_rows)} |",
          f"| Same request twice, identical | {summary['repeats'][0]} of {summary['repeats'][1]} | {sum(s for _, s in repeats)} of {len(repeats)} |",
          f"| Quoted text found in a retrieved document | {summary['quotes'][0]} of {summary['quotes'][1]} | {sum(q for _, q in quotes)} of {len(quotes)} |",
          f"| Checker: bad replies rejected | {summary['bad_rejected']} of 5 | |",
          f"| Checker: good reply accepted | {summary['good_accepted']} of 1 | |",
          f"| Average top meaning-search score on hits | {summary['avg_hit']:.3f} | |" if summary["avg_hit"] is not None else "| Average top score on hits | n/a | |",
          f"| Average top score on the no-match cases | {summary['avg_no_match']:.3f} | |" if summary["avg_no_match"] is not None else "| Average top score on no-match cases | n/a | |",
          "", "## Retrieval requests", ""] + out + ["## Guardrail cases", "",
          "| case | input | expected behavior | what happened | result |", "|---|---|---|---|---|"] + \
         [i["_row"] for i in items if i["type"] == "guardrail"] + ["", "## Checker on bad replies (no network)", "",
          "| reply | should be | result | why |", "|---|---|---|---|"] + \
         [f"| {label} | {'accepted' if should else 'rejected'} | {'accepted' if accepted else 'rejected'} | {problem or 'passes every check'} |"
          for label, should, accepted, problem in checker_rows] + ["", "## Repeat runs and quotes", "",
          "| item | same request twice identical | answer carries cited text | quote found |", "|---|---|---|---|"] + \
         [f"| {i} | {'yes' if same else '**NO**'} | {'yes' if any(q[0] == i for q in quotes) else 'no'} | "
          f"{('yes' if dict(quotes)[i] else '**NO**') if i in dict(quotes) else 'n/a'} |" for i, same in repeats] + ["", "## Flagged rows", ""] + \
         ([f"- {f}" for f in flagged] or ["- none"])
    return "\n".join(md) + "\n", summary


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.evaluate", description="Run the golden set against the search system.")
    parser.add_argument("--with-gemini", action="store_true", help="let the answer writer call Gemini (needs a key); default is no Gemini calls")
    args = parser.parse_args(argv)
    markdown, _ = evaluate(with_gemini=args.with_gemini)
    target = RESULTS_GEMINI_PATH if args.with_gemini else RESULTS_PATH
    target.write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"Wrote {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
