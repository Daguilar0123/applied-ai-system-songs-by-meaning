"""Tests for load_songs (Phase 3 Step 1): the CSV comes back as dicts with real numbers."""
from pathlib import Path

import pytest

from src.recommender import NUMERIC_FIELDS, SONGS_CSV, load_songs

# data/songs.csv, located from the code's own file location (src/recommender.py), not from the working folder.
CSV_PATH = str(SONGS_CSV)

REQUIRED_COLUMNS = (
    "id", "title", "artist", "genre", "mood",
    "energy", "tempo_bpm", "valence", "danceability", "acousticness",
)


def test_at_least_fifteen_songs():
    songs = load_songs(CSV_PATH)
    assert len(songs) >= 15


def test_numeric_fields_are_floats():
    for song in load_songs(CSV_PATH):
        for field in NUMERIC_FIELDS:
            assert isinstance(song[field], float), f"{song['title']}: {field} is {type(song[field]).__name__}"
        assert isinstance(song["id"], int), f"{song['title']}: id is {type(song['id']).__name__}"


def test_required_columns_present():
    for song in load_songs(CSV_PATH):
        for column in REQUIRED_COLUMNS:
            assert column in song, f"{song.get('title')} is missing column {column}"


def test_genres_are_diverse():
    genres = {song["genre"] for song in load_songs(CSV_PATH)}
    assert len(genres) >= 12


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_songs(str(Path(CSV_PATH).with_name("no_such_songs.csv")))


def test_songs_csv_path_comes_from_the_code_not_the_working_folder(tmp_path, monkeypatch, capsys):
    from src.main import main
    assert SONGS_CSV.is_absolute() and SONGS_CSV.exists()
    monkeypatch.chdir(tmp_path)                       # an empty folder with no data/ in it
    main(["--profile", "pop_happy", "--k", "1"])
    assert "Loaded songs: 20" in capsys.readouterr().out
