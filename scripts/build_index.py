"""Build the search index files from the library.

    .venv/bin/python scripts/build_index.py

Writes data/song_vectors.json (one record per lyric verse and per APPROVED description: song id, title, kind, text,
embedding) and data/demo_query_vectors.json (saved vectors for the five demo requests, so a demo still runs if the
embedding model cannot be downloaded). Descriptions with "approved": false are left out.
"""
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

try:
    from scripts.build_song_list import parse_lyrics_file
    from scripts.library_catalog import slugify
except ImportError:  # running as `python scripts/build_index.py`
    from build_song_list import parse_lyrics_file
    from library_catalog import slugify

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
LYRICS_DIR = ROOT / "data" / "library" / "lyrics"
DESCRIPTIONS = ROOT / "data" / "library" / "descriptions.json"
VECTORS_PATH = ROOT / "data" / "song_vectors.json"
DEMO_PATH = ROOT / "data" / "demo_query_vectors.json"

# Five demo requests, each worded without copying the stored text, with the song id a good search should return.
DEMO_REQUESTS = [
    {"request": "a woman begs a beautiful rival not to take her husband", "expect": "jolene"},
    {"request": "a rapper reflects on racism, police violence and how little has changed", "expect": "changes"},
    {"request": "a call to free an enslaved people, told through the Bible", "expect": "go-down-moses"},
    {"request": "snacks at the stadium and rooting for the home team", "expect": "take-me-out-to-the-ball-game"},
    {"request": "the Caped Crusader mocked in a playground version of a Christmas song", "expect": "jingle-bells-batman-parody"},
]


def build_documents(lyrics_dir: Path, descriptions_path: Path) -> List[Dict]:
    """The documents to embed: each verse of each lyric file, then each approved description. No embeddings yet."""
    docs: List[Dict] = []
    if lyrics_dir.is_dir():
        for path in sorted(lyrics_dir.glob("*.txt")):
            lyric = parse_lyrics_file(path)
            song_id = slugify(lyric["title"])
            for n, verse in enumerate(lyric["verses"], start=1):
                docs.append({"doc_id": f"{song_id}#{n}", "song_id": song_id, "title": lyric["title"],
                             "kind": "lyrics", "text": verse, "source": lyric["source"]})
    drafted = json.loads(descriptions_path.read_text(encoding="utf-8")) if descriptions_path.exists() else []
    for item in drafted:
        if item.get("approved"):
            docs.append({"doc_id": f"{item['id']}#description", "song_id": item["id"], "title": item["title"],
                         "kind": "description", "text": item["description"], "source": item["wikipedia_url"]})
    return docs


def main(argv: Optional[List[str]] = None) -> int:
    from src.embedder import EMBED_DIM, MODEL_NAME, embed
    docs = build_documents(LYRICS_DIR, DESCRIPTIONS)
    if not docs:
        print("No documents found; nothing written.", file=sys.stderr)
        return 1
    for doc, vector in zip(docs, embed([d["text"] for d in docs])):
        doc["embedding"] = [round(x, 6) for x in vector]
    VECTORS_PATH.write_text(json.dumps({"model": MODEL_NAME, "dim": EMBED_DIM, "documents": docs}) + "\n", encoding="utf-8")
    demo = [{"request": d["request"], "expect": d["expect"], "embedding": [round(x, 6) for x in v]}
            for d, v in zip(DEMO_REQUESTS, embed([d["request"] for d in DEMO_REQUESTS]))]
    DEMO_PATH.write_text(json.dumps({"model": MODEL_NAME, "dim": EMBED_DIM, "requests": demo}) + "\n", encoding="utf-8")
    kinds = {k: sum(d["kind"] == k for d in docs) for k in ("lyrics", "description")}
    print(f"Wrote {len(docs)} documents ({kinds['lyrics']} verses, {kinds['description']} descriptions) to {VECTORS_PATH.relative_to(ROOT)}")
    print(f"Wrote {len(demo)} demo request vectors to {DEMO_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
