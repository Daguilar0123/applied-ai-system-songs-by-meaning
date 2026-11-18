"""Step 3 tests: the checker rejects each kind of bad Gemini reply on purpose, and passes a good one. No network."""
import json

from src.answer import ask_gemini, build_prompt
from src.checker import FALLBACK_REASON, check_answer

HITS = [
    {"song_id": "jolene", "title": "Jolene", "kind": "description", "score": 0.85,
     "text": "The narrator begs a beautiful woman not to take her husband."},
    {"song_id": "take-me-out", "title": "Take Me Out", "kind": "lyrics", "score": 0.80,
     "text": "Buy me some peanuts and Cracker Jack,\nI don't care if I never get back."},
    {"song_id": "jolene", "title": "Jolene", "kind": "lyrics", "score": 0.78,
     "text": "Please don't take him just because you can."},
]


def reply(**fields):
    base = {"song_id": "jolene", "reason": "The request describes a plea to a rival.",
            "cited_text": "begs a beautiful woman not to take her husband"}
    base.update(fields)
    return json.dumps(base)


def test_a_good_reply_passes():
    result = check_answer(reply(), HITS)
    assert result["fallback"] is False and result["problem"] is None
    assert result["song_id"] == "jolene" and result["title"] == "Jolene"
    assert result["cited_text"] == "begs a beautiful woman not to take her husband"


def test_cited_text_may_differ_in_case_and_line_breaks():
    assert check_answer(reply(song_id="take-me-out", cited_text="buy me some PEANUTS and cracker jack, I don't care"), HITS)["fallback"] is False


def test_cited_text_may_come_from_any_retrieved_document_of_that_song():
    assert check_answer(reply(cited_text="Please don't take him just because you can."), HITS)["fallback"] is False


def rejected(raw, expect_in_problem):
    result = check_answer(raw, HITS)
    assert result["fallback"] is True, raw
    assert expect_in_problem in result["problem"], result["problem"]
    assert result["song_id"] == "jolene" and result["reason"] == FALLBACK_REASON      # plain answer from the top hit
    assert result["cited_text"] == HITS[0]["text"]
    return result


def test_rejects_a_reply_that_is_not_json():
    rejected("Sure! The song you want is Jolene.", "not valid JSON")
    rejected("```json\n" + reply() + "\n```", "not valid JSON")


def test_rejects_json_that_is_not_an_object():
    rejected(json.dumps(["jolene"]), "not a JSON object")
    rejected(json.dumps("jolene"), "not a JSON object")


def test_rejects_a_missing_or_empty_field():
    for field in ("song_id", "reason", "cited_text"):
        body = json.loads(reply())
        del body[field]
        rejected(json.dumps(body), field)
        rejected(reply(**{field: ""}), field)


def test_rejects_a_song_that_was_not_retrieved():
    rejected(reply(song_id="fast-car"), "not among the retrieved")


def test_rejects_cited_text_that_is_not_in_that_songs_documents():
    rejected(reply(cited_text="a line Gemini made up"), "not found in")
    rejected(reply(cited_text="peanuts and Cracker Jack"), "not found in")     # real text, but from a different song


def test_rejects_a_citation_too_short_to_mean_anything():
    rejected(reply(cited_text="y"), "shorter than")
    rejected(reply(cited_text="the song"), "shorter than")


def test_no_gemini_reply_gives_the_plain_answer_marked_fallback():
    result = check_answer(None, HITS)
    assert result["fallback"] is True and "no Gemini reply" in result["problem"]
    assert result["song_id"] == "jolene" and result["cited_text"] == HITS[0]["text"]


def test_no_hits_gives_no_answer_and_no_crash():
    result = check_answer(reply(), [])
    assert result["fallback"] is True and result["song_id"] is None


# ---- the answer writer, without a key ----

def test_prompt_holds_only_the_request_and_the_retrieved_documents():
    prompt = build_prompt("a plea to a rival", HITS)
    assert "a plea to a rival" in prompt
    for hit in HITS:
        assert hit["song_id"] in prompt and hit["text"] in prompt


def test_with_no_key_the_call_is_skipped(monkeypatch):
    import src.answer as answer
    monkeypatch.setattr(answer, "get_api_key", lambda: "")
    monkeypatch.setattr(answer, "_call_gemini", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called")))
    assert ask_gemini("anything", HITS) == {"raw": None, "status": "no key: call skipped"}
