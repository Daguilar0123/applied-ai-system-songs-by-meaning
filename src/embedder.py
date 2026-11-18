"""Local text embedder: fastembed with BAAI/bge-small-en-v1.5. Needs no key. The same model embeds the library
documents (at build time) and every search request, so their vectors are comparable."""
from typing import List

MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBED_DIM = 384          # the one dimension constant; Atlas's index (Step 6) must use this same value

_model = None


def _get_model():
    """Load the model once (about 66 MB, downloaded on first use, then cached on disk)."""
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(MODEL_NAME)
    return _model


def embed(texts: List[str]) -> List[List[float]]:
    """One list of EMBED_DIM floats per text, in order. An empty list in gives an empty list out."""
    if not texts:
        return []
    return [[float(x) for x in vector] for vector in _get_model().embed(texts)]
