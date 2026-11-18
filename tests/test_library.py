"""Step 1 tests: the song library builders. No network, no keys, no real data files (everything lives in tmp_path)."""
import json

from scripts.library_catalog import MODERN, STARTER_IDS, slugify
from scripts.draft_descriptions import (build_source_text, extract_sections, merge_record, violates_guard)
from scripts.build_song_list import build_records, parse_lyrics_file, render_attribution

ARTICLE = (
    "Intro line about the song.\n\n\n"
    "== Background ==\nBackground text.\n\n"
    "=== A sub-heading ===\nSub text under background.\n\n"
    "== Content ==\nContent text.\n\n"
    "== Charts ==\nChart text.\n"
)


def test_extract_sections_keeps_named_sections_and_their_subsections():
    text = extract_sections(ARTICLE, ["Background", "Content"])
    assert "Background text." in text
    assert "Sub text under background." in text      # a level-3 heading stays inside its level-2 section
    assert "Content text." in text
    assert "Chart text." not in text
    assert "Intro line" not in text


def test_extract_sections_missing_heading_gives_empty_string():
    assert extract_sections(ARTICLE, ["Nope"]) == ""


def test_source_text_uses_summary_plus_sections():
    entry = {"sections": ("Content",), "use_summary": True}
    article = {"summary": "Short summary.", "full_text": ARTICLE}
    text = build_source_text(article, entry)
    assert "Short summary." in text and "Content text." in text and "Chart text." not in text


def test_source_text_for_the_parody_leaves_out_the_summary():
    entry = {"sections": ("Content",), "use_summary": False}
    article = {"summary": "Short summary.", "full_text": ARTICLE}
    assert "Short summary." not in build_source_text(article, entry)


def test_source_text_can_keep_only_the_first_paragraph():
    article = {"summary": "", "full_text": "== Content ==\nFirst paragraph.\nSecond paragraph.\n"}
    text = build_source_text(article, {"sections": ("Content",), "use_summary": False, "max_paragraphs": 1})
    assert text == "First paragraph."


def test_merge_never_overwrites_an_approved_description():
    old = {"id": "x", "description": "Danny's edit", "approved": True}
    new = {"id": "x", "description": "fresh draft", "approved": False}
    assert merge_record(old, new, force=True) == old
    assert merge_record(old, new, force=False) == old


def test_merge_keeps_an_unapproved_draft_unless_forced():
    old = {"id": "x", "description": "old draft", "approved": False}
    new = {"id": "x", "description": "fresh draft", "approved": False}
    assert merge_record(old, new, force=False) == old
    assert merge_record(old, new, force=True) == new
    assert merge_record(None, new, force=False) == new


def test_guard_blocks_the_batman_parody_line_in_any_case():
    assert violates_guard("Kids sing that Batman smells.")
    assert violates_guard("BATMAN SMELLS, they chant")
    assert not violates_guard("A playground parody that mocks a comic-book hero.")


def test_catalog_starter_set_is_five_descriptions_including_changes_and_the_parody():
    assert len(STARTER_IDS) == 5
    assert "changes" in STARTER_IDS and "jingle-bells-batman-parody" in STARTER_IDS
    assert all(e["energy"] is not None and 0 <= e["energy"] <= 1 for e in MODERN)


def test_slugify():
    assert slugify("St. Louis Blues") == "st-louis-blues"
    assert slugify("What Was I Made For?") == "what-was-i-made-for"


def _write_lyrics(folder, name, title, year, source):
    (folder / f"{name}.txt").write_text(
        f"title: {title}\nyear: {year}\nsource: {source}\nfetched: 2026-11-17\n\nFirst verse line one\nline two\n\nSecond verse\n",
        encoding="utf-8")


def test_parse_lyrics_file_reads_headers_and_verses(tmp_path):
    _write_lyrics(tmp_path, "amazing-grace", "Amazing Grace", 1779, "https://en.wikisource.org/wiki/x")
    rec = parse_lyrics_file(tmp_path / "amazing-grace.txt")
    assert rec["title"] == "Amazing Grace" and rec["year"] == 1779
    assert rec["source"] == "https://en.wikisource.org/wiki/x"
    assert len(rec["verses"]) == 2


def test_build_records_joins_lyrics_and_descriptions(tmp_path):
    lyrics = tmp_path / "lyrics"
    lyrics.mkdir()
    _write_lyrics(lyrics, "amazing-grace", "Amazing Grace", 1779, "https://en.wikisource.org/wiki/x")
    _write_lyrics(lyrics, "mystery-tune", "Mystery Tune", 1900, "https://en.wikisource.org/wiki/y")
    desc = tmp_path / "descriptions.json"
    desc.write_text(json.dumps([{"id": "changes", "title": "Changes", "wikipedia_url": "https://en.wikipedia.org/wiki/C",
                                 "revision_id": 1, "description": "d", "approved": False}]), encoding="utf-8")
    recs = {r["id"]: r for r in build_records(lyrics, desc)}
    grace = recs["amazing-grace"]
    assert grace["kind"] == "lyrics" and grace["genre"] == "folk"        # `genre` is only the scorer's nearest word
    assert grace["genre_label"] == "Christian hymn" and grace["genre_label_source"] == "Wikipedia infobox"
    assert recs["mystery-tune"]["genre"] is None and recs["mystery-tune"]["genre_label"] is None   # left blank, not guessed
    assert recs["changes"]["kind"] == "description" and recs["changes"]["genre"] == "hip-hop"
    assert recs["changes"]["source"] == "https://en.wikipedia.org/wiki/C"
    assert recs["changes"]["genre_label"] == "Conscious hip-hop"
    known = [r for r in recs.values() if r["id"] != "mystery-tune"]
    assert all(r["mood_energy_source"] == "estimate" and r["accepted"] for r in known)   # mood and energy are labeled estimates
    assert recs["mystery-tune"]["mood_energy_source"] is None


def test_build_records_works_when_the_lyrics_folder_is_missing(tmp_path):
    desc = tmp_path / "descriptions.json"
    desc.write_text("[]", encoding="utf-8")
    assert build_records(tmp_path / "no-such-folder", desc) == []


def test_attribution_names_cc_by_sa_each_article_and_each_lyric_source(tmp_path):
    records = [
        {"id": "amazing-grace", "title": "Amazing Grace", "kind": "lyrics", "source": "https://en.wikisource.org/wiki/x"},
        {"id": "changes", "title": "Changes", "kind": "description", "source": "https://en.wikipedia.org/wiki/C"},
    ]
    descriptions = [{"id": "changes", "wikipedia_url": "https://en.wikipedia.org/wiki/C", "revision_id": 1381254516}]
    text = render_attribution(records, descriptions)
    assert "CC BY-SA 4.0" in text and "https://creativecommons.org/licenses/by-sa/4.0/" in text
    assert "https://en.wikipedia.org/wiki/C" in text and "1381254516" in text
    assert "https://en.wikisource.org/wiki/x" in text and "Public domain" in text
    assert "estimates" in text and "`genre_label`" in text      # the genre/mood/energy section is present


def test_attribution_says_when_a_lyric_was_copied_from_a_wikipedia_article():
    records = [
        {"id": "go-down-moses", "title": "Go Down, Moses", "kind": "lyrics", "year": 1872,
         "source": "https://en.wikipedia.org/wiki/Go_Down_Moses"},
        {"id": "danny-boy", "title": "Danny Boy", "kind": "lyrics", "year": 1913,
         "source": "https://en.wikisource.org/wiki/Danny_Boy"},
    ]
    lines = render_attribution(records, []).splitlines()
    moses = next(l for l in lines if l.startswith("- Go Down, Moses"))
    boy = next(l for l in lines if l.startswith("- Danny Boy"))
    assert "Wikipedia article, which quotes the 1872 text" in moses
    assert "Wikipedia article" not in boy
