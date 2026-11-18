"""Step 4 tests: the --search command, its trace table and the trace log line. Gemini is always faked; nothing hits the network."""
import json

import pytest

import src.search_cli as search_cli
from src.main import main, parse_args

GOOD = json.dumps({"song_id": "jolene", "reason": "The request describes a plea to a rival.",
                   "cited_text": "a direct plea begging that woman not to steal away her partner"})
REQUEST = "a woman begs a beautiful rival not to take her husband"


@pytest.fixture
def trace_file(tmp_path, monkeypatch):
    path = tmp_path / "logs" / "search_trace.jsonl"
    monkeypatch.setattr(search_cli, "TRACE_PATH", path)
    return path


def fake_gemini(monkeypatch, raw, status="ok"):
    calls = []
    monkeypatch.setattr(search_cli, "ask_gemini", lambda request, hits: calls.append(request) or {"raw": raw, "status": status})
    return calls


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_a_checked_gemini_answer_is_printed_with_its_trace(trace_file, monkeypatch):
    fake_gemini(monkeypatch, GOOD)
    out = search_cli.run_search(REQUEST)
    assert "Jolene" in out and "plea to a rival" in out
    assert "check     : pass" in out and "decision  : checked Gemini answer" in out
    assert out.count("0.") >= 3                                   # the top three scores are in the table
    (record,) = lines(trace_file)
    assert record["request"] == REQUEST and record["check"] == "pass" and record["decision"] == "checked Gemini answer"
    assert len(record["top3"]) == 3 and record["answer"]["song_id"] == "jolene"


def test_a_rejected_reply_gives_the_plain_answer_marked_fallback(trace_file, monkeypatch):
    fake_gemini(monkeypatch, json.dumps({"song_id": "jolene", "reason": "r", "cited_text": "made up words"}))
    out = search_cli.run_search(REQUEST)
    assert "fallback" in out and "rejected" in out and "Jolene" in out
    (record,) = lines(trace_file)
    assert record["decision"] == "fallback: top match" and record["check"].startswith("rejected")


def test_no_key_skips_the_call_and_still_answers(trace_file, monkeypatch):
    fake_gemini(monkeypatch, None, status="no key: call skipped")
    out = search_cli.run_search(REQUEST)
    assert "skipped" in out and "fallback" in out and "Jolene" in out
    assert lines(trace_file)[0]["gemini_status"] == "no key: call skipped"


def test_a_far_off_request_says_nothing_close_and_never_calls_gemini(trace_file, monkeypatch):
    calls = fake_gemini(monkeypatch, GOOD)
    out = search_cli.run_search("quarterly tax filing deadlines for small businesses")
    assert "nothing close found" in out and calls == []
    assert lines(trace_file)[0]["decision"] == "nothing close found"


def test_an_empty_request_is_handled(trace_file, monkeypatch):
    calls = fake_gemini(monkeypatch, GOOD)
    out = search_cli.run_search("   ")
    assert "empty" in out.lower() and calls == []
    assert len(lines(trace_file)) == 1


def test_each_search_appends_one_line(trace_file, monkeypatch):
    fake_gemini(monkeypatch, GOOD)
    search_cli.run_search(REQUEST)
    search_cli.run_search("let my people go")
    assert len(lines(trace_file)) == 2


def test_kind_filter_reaches_the_search(trace_file, monkeypatch):
    fake_gemini(monkeypatch, None, status="no key: call skipped")
    search_cli.run_search("a call to free an enslaved people", kind="lyrics")
    assert {hit["kind"] for hit in lines(trace_file)[0]["top3"]} == {"lyrics"}


def test_long_gemini_replies_are_shortened_in_the_table(trace_file, monkeypatch):
    long_reply = json.dumps({"song_id": "jolene", "reason": "x" * 500,
                             "cited_text": "a direct plea begging that woman not to steal away her partner"})
    fake_gemini(monkeypatch, long_reply)
    table = search_cli.run_search(REQUEST).split("--- trace ---")[1]
    assert "gemini    :" in table and "x" * 200 not in table and "..." in table


def test_main_wires_search_and_kind(trace_file, monkeypatch, capsys):
    fake_gemini(monkeypatch, None, status="no key: call skipped")
    main(["--search", "a call to free an enslaved people", "--kind", "lyrics"])
    out = capsys.readouterr().out
    assert "Go Down, Moses" in out and "Loaded songs" not in out       # search mode does not run the profile recommender


def test_kind_without_search_is_an_error():
    with pytest.raises(SystemExit):
        parse_args(["--kind", "lyrics"])


def test_the_existing_profile_run_is_unchanged(capsys):
    main(["--profile", "pop_happy", "--k", "2"])
    assert "Loaded songs: 20" in capsys.readouterr().out


# ---- the 300-character limit on requests ----

def test_a_request_over_300_characters_is_refused_with_a_clear_message(trace_file, monkeypatch):
    calls = fake_gemini(monkeypatch, GOOD)
    out = search_cli.run_search("a" * 301)
    assert "too long" in out and "301" in out and "300" in out
    assert calls == [] and "Answer" not in out                      # no search answer, and Gemini is never called
    (record,) = lines(trace_file)
    assert record["decision"] == "request too long" and record["top3"] == []


def test_a_request_of_exactly_300_characters_is_allowed(trace_file, monkeypatch):
    fake_gemini(monkeypatch, None, status="no key: call skipped")
    out = search_cli.run_search("let my people go " + "x" * 283)
    assert len("let my people go " + "x" * 283) == 300 and "too long" not in out
    assert lines(trace_file)[0]["decision"] != "request too long"


def test_surrounding_spaces_do_not_count_toward_the_limit(trace_file, monkeypatch):
    fake_gemini(monkeypatch, None, status="no key: call skipped")
    assert "too long" not in search_cli.run_search("   let my people go   " + " " * 400)


def test_search_itself_returns_nothing_for_an_over_long_request():
    from src.song_search import MAX_REQUEST_CHARS, search
    assert MAX_REQUEST_CHARS == 300 and search("a" * 301) == []


def test_main_prints_the_message_for_an_over_long_search(trace_file, monkeypatch, capsys):
    fake_gemini(monkeypatch, GOOD)
    main(["--search", "word " * 80])
    assert "too long" in capsys.readouterr().out
