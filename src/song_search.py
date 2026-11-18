"""Search the song library by meaning (and, for comparison, by plain word matching).

search(request, k=3, kind=None) embeds the request with the local model and ranks the saved document vectors
(data/song_vectors.json) by cosine similarity with NumPy. Each hit: song_id, title, kind, text, score (0 to 1).
It always returns the top k; nothing_close(hits) says whether the best one is too weak to trust (below MIN_SCORE).
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

try:
    from src import embedder
except ImportError:  # running as `python src/main.py`
    import embedder

ROOT = Path(__file__).resolve().parent.parent
VECTORS_PATH = ROOT / "data" / "song_vectors.json"
DEMO_PATH = ROOT / "data" / "demo_query_vectors.json"
MIN_SCORE = 0.78         # below this best score the answer is "nothing close found". Chosen Nov 18, 2026 from real scores:
#                          good matches scored 0.83 to 0.89, off-topic requests 0.71 to 0.76 (README has the table)
NOTHING_CLOSE = "nothing close found"
MAX_REQUEST_CHARS = 300   # longest request accepted (spaces at either end do not count); decided Nov 18, 2026

_index: Optional[Dict] = None
_STOPWORDS = frozenset("a an and are as at be but by for from has have he her his i if in into is it its me my no not of on or "
                       "she so than that the their them they this to up was we were what when which who will with you your".split())


def _load_index() -> Dict:
    """Read the saved vectors once; keep a unit-length matrix so cosine is a dot product."""
    global _index
    if _index is None:
        data = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
        matrix = np.array([d["embedding"] for d in data["documents"]], dtype=np.float32)
        matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
        _index = {"docs": data["documents"], "matrix": matrix}
    return _index


def _query_vector(request: str) -> Optional[List[float]]:
    """Embed the request locally; if the model cannot load (no internet on first use), try the saved demo vectors."""
    try:
        return embedder.embed([request])[0]
    except Exception:
        if DEMO_PATH.exists():
            for item in json.loads(DEMO_PATH.read_text(encoding="utf-8"))["requests"]:
                if item["request"] == request:
                    return item["embedding"]
        return None


def _hit(doc: Dict, score: float) -> Dict:
    return {"song_id": doc["song_id"], "title": doc["title"], "kind": doc["kind"], "text": doc["text"], "score": round(score, 4)}


def search(request: str, k: int = 3, kind: Optional[str] = None) -> List[Dict]:
    """Top-k documents by meaning, best first. An empty or over-long request, or one that cannot be embedded, gives []."""
    if not request or not request.strip() or len(request.strip()) > MAX_REQUEST_CHARS:
        return []
    vector = _query_vector(request.strip())
    if vector is None:
        return []
    index = _load_index()
    q = np.asarray(vector, dtype=np.float32)
    q /= np.linalg.norm(q)
    cosine = index["matrix"] @ q
    order = [i for i in np.argsort(-cosine) if kind in (None, index["docs"][i]["kind"])][:k]
    return [_hit(index["docs"][i], float((1 + cosine[i]) / 2)) for i in order]     # (1 + cos) / 2 puts the score on 0 to 1


def nothing_close(hits: List[Dict]) -> bool:
    """True when there are no hits, or the best score is below MIN_SCORE."""
    return not hits or hits[0]["score"] < MIN_SCORE


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in _STOPWORDS}


def keyword_search(request: str, k: int = 3) -> List[Dict]:
    """Plain word matching over the same texts: score = share of the request's words that appear in the document."""
    wanted = _words(request or "")
    if not wanted:
        return []
    scored = []
    for doc in _load_index()["docs"]:
        overlap = len(wanted & _words(doc["text"]))
        if overlap:
            scored.append((overlap / len(wanted), doc))
    scored.sort(key=lambda pair: -pair[0])
    return [_hit(doc, score) for score, doc in scored[:k]]
