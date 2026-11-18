"""Tests for the evaluation script's helpers and the golden set. No network, no keys, no search."""
import json

from src.evaluate import GOLDEN_PATH, hit_rate, load_golden, shared_words

SONGS_JSON = GOLDEN_PATH.parent.parent / "data" / "library" / "songs.json"
RETRIEVAL_FIELDS = {"id", "type", "request", "hit_song_ids", "shares_important_word_with_lyric", "approved_by_danny"}
GUARDRAIL_FIELDS = {"id", "type", "case", "request", "expected", "pass_rule", "approved_by_danny"}
PASS_RULES = {"handled_empty", "no_match", "injection_resisted"}


def test_golden_set_loads_and_every_item_has_its_fields():
    golden = load_golden()
    assert golden["k"] == 3 and len(golden["items"]) == 10
    for item in golden["items"]:
        assert item["type"] in ("retrieval", "guardrail")
        needed = RETRIEVAL_FIELDS if item["type"] == "retrieval" else GUARDRAIL_FIELDS
        assert needed <= set(item), item["id"]
        assert isinstance(item["approved_by_danny"], bool)
        if item["type"] == "guardrail":
            assert item["pass_rule"] in PASS_RULES
            if item["pass_rule"] == "injection_resisted":
                assert item["forbidden_in_answer"] and item["hit_song_ids"]
        else:
            assert item["hit_song_ids"] and isinstance(item["shares_important_word_with_lyric"], bool)


def test_every_expected_song_id_is_in_songs_json():
    known = {song["id"] for song in json.loads(SONGS_JSON.read_text(encoding="utf-8"))}
    for item in load_golden()["items"]:
        for song_id in item.get("hit_song_ids", []):
            assert song_id in known, (item["id"], song_id)


ROWS = [  # made up: 3 requests sharing no word (2 approved, 1 not) and 2 controls (both approved)
    {"id": "a", "approved": True, "shares_important_word": False, "meaning_hit3": True, "word_hit3": False},
    {"id": "b", "approved": True, "shares_important_word": False, "meaning_hit3": True, "word_hit3": False},
    {"id": "c", "approved": False, "shares_important_word": False, "meaning_hit3": False, "word_hit3": False},
    {"id": "d", "approved": True, "shares_important_word": True, "meaning_hit3": True, "word_hit3": True},
    {"id": "e", "approved": True, "shares_important_word": True, "meaning_hit3": False, "word_hit3": True},
]


def test_hit_rate_gives_the_right_numbers_on_a_small_example():
    assert hit_rate(ROWS, "meaning_hit3", shares_important_word=False) == (2, 2)
    assert hit_rate(ROWS, "word_hit3", shares_important_word=False) == (0, 2)
    assert hit_rate(ROWS, "meaning_hit3", shares_important_word=True) == (1, 2)
    assert hit_rate(ROWS, "word_hit3", shares_important_word=True) == (2, 2)


def test_unapproved_items_are_left_out_of_the_headline_count_but_counted_in_the_all_items_line():
    assert hit_rate(ROWS, "meaning_hit3", shares_important_word=False, approved_only=True) == (2, 2)
    assert hit_rate(ROWS, "meaning_hit3", shares_important_word=False, approved_only=False) == (2, 3)


def test_shared_words_lowercases_and_drops_stop_words():
    shared = shared_words("a girl who turns down THE night at the ball game", "Take me out to the ball game, the Night is down")
    assert shared == ["ball", "game", "night"]      # "down", "the", "at", "a", "who" are stop words
    assert shared_words("", "anything") == []
