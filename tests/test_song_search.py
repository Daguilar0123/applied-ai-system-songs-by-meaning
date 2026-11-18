"""Step 2 tests: the embedder, the index builder's document list, and search. Real model, real saved vectors, no keys."""
import json

import pytest

from src import embedder, song_search
from src.song_search import MIN_SCORE, keyword_search, nothing_close, search
from scripts.build_index import DEMO_REQUESTS, build_documents


@pytest.fixture(autouse=True)
def no_environment(monkeypatch):
    """Search must work with no environment variables set (no Gemini key, no Atlas string)."""
    for name in ("GEMINI_API_KEY", "MONGODB_URI"):
        monkeypatch.delenv(name, raising=False)


def test_embedder_returns_384_numbers_per_text():
    assert embedder.EMBED_DIM == 384
    vectors = embedder.embed(["a song about a river", "another one"])
    assert len(vectors) == 2 and all(len(v) == embedder.EMBED_DIM for v in vectors)
    assert embedder.embed([]) == []


def test_known_request_finds_the_right_song():
    hits = search("a woman begs a beautiful rival not to take her husband", k=3)
    assert hits[0]["song_id"] == "jolene"
    assert set(hits[0]) >= {"song_id", "title", "kind", "text", "score"}
    assert 0.0 <= hits[0]["score"] <= 1.0 and not nothing_close(hits)


def test_hits_come_back_best_first_and_k_is_respected():
    hits = search("let my people go", k=2)
    assert len(hits) == 2 and hits[0]["score"] >= hits[1]["score"]


def test_kind_filter_only_returns_that_kind():
    for kind in ("lyrics", "description"):
        hits = search("a song about leaving home", k=5, kind=kind)
        assert hits and all(h["kind"] == kind for h in hits)


def test_empty_request_is_handled_without_a_crash():
    assert search("") == [] and search("   ") == []
    assert keyword_search("") == []


def test_far_off_request_is_flagged_as_nothing_close():
    hits = search("quarterly tax filing deadlines for small businesses", k=3)
    assert nothing_close(hits)
    assert nothing_close([])           # no hits at all counts as nothing close


def test_min_score_sits_between_a_real_match_and_a_far_off_request():
    good = search("a woman begs a beautiful rival not to take her husband")[0]["score"]
    far = search("quarterly tax filing deadlines for small businesses")[0]["score"]
    assert far < MIN_SCORE <= good


def test_keyword_search_matches_words_and_misses_a_paraphrase():
    assert keyword_search("peanuts Cracker Jack")[0]["song_id"] == "take-me-out-to-the-ball-game"
    paraphrase = "buying snacks at the stadium"      # no word in common with the verse, so word matching finds nothing
    assert keyword_search(paraphrase) == []
    assert search(paraphrase, k=3)[0]["song_id"] == "take-me-out-to-the-ball-game"


def test_search_falls_back_to_saved_demo_vectors_when_the_model_cannot_load(monkeypatch):
    def broken(_texts):
        raise OSError("model download failed")
    monkeypatch.setattr(song_search.embedder, "embed", broken)
    demo = DEMO_REQUESTS[0]
    assert search(demo["request"], k=1)[0]["song_id"] == demo["expect"]     # served from data/demo_query_vectors.json
    assert search("a request that was never saved", k=1) == []             # no saved vector either: nothing, no crash


def test_every_demo_request_finds_its_song_in_the_top_three():
    for demo in DEMO_REQUESTS:
        assert demo["expect"] in [h["song_id"] for h in search(demo["request"], k=3)], demo["request"]


# ---- the index builder's document list (no model needed) ----

def _lyrics(folder, name, verses):
    (folder / f"{name}.txt").write_text("title: " + name.title() + "\nyear: 1900\nsource: https://x\nfetched: 2026-11-17\n\n"
                                        + "\n\n".join(verses) + "\n", encoding="utf-8")


def test_build_documents_one_per_verse_and_only_approved_descriptions(tmp_path):
    lyrics = tmp_path / "lyrics"
    lyrics.mkdir()
    _lyrics(lyrics, "tune", ["verse one\nline two", "verse two"])
    desc = tmp_path / "d.json"
    desc.write_text(json.dumps([
        {"id": "a", "title": "A", "wikipedia_url": "https://w/a", "description": "approved text", "approved": True},
        {"id": "b", "title": "B", "wikipedia_url": "https://w/b", "description": "draft text", "approved": False}]))
    docs = build_documents(lyrics, desc)
    assert [d["kind"] for d in docs] == ["lyrics", "lyrics", "description"]
    assert [d["text"] for d in docs] == ["verse one\nline two", "verse two", "approved text"]
    assert all(set(d) >= {"doc_id", "song_id", "title", "kind", "text", "source"} for d in docs)
    assert docs[0]["song_id"] == "tune"
