"""BM25 sparse vectors with own tokenization pipeline.

German pipeline: lowercase -> decompound -> remove stopwords -> stem (Snowball).
English pipeline: lowercase -> remove stopwords -> stem (Snowball).
Output: dict {token_index: bm25_score} usable as Qdrant SparseVector.

We own this pipeline — we don't rely on Qdrant's analyzer for German decompounding.
"""
from __future__ import annotations
import re
import math
from functools import lru_cache

import nltk
from nltk.corpus import stopwords
from nltk.stem import SnowballStemmer
from rank_bm25 import BM25Okapi

# ── NLTK downloads (silent; already fetched at setup) ─────────────────────
try:
    _STOPWORDS_DE = set(stopwords.words("german"))
    _STOPWORDS_EN = set(stopwords.words("english"))
except LookupError:
    nltk.download("stopwords", quiet=True)
    _STOPWORDS_DE = set(stopwords.words("german"))
    _STOPWORDS_EN = set(stopwords.words("english"))

_STEMMER_DE = SnowballStemmer("german")
_STEMMER_EN = SnowballStemmer("english")

# ── German compound splitting ──────────────────────────────────────────────
# Common German linking morphemes (Fugenelemente) used between compound parts.
_FUGE = ("s", "es", "en", "er", "e", "ens")
# Minimum length for a compound part to be kept (avoids single-letter splits)
_MIN_PART_LEN = 3

# Common German prefixes that should not be stripped as compound parts
_DE_PREFIXES = frozenset([
    "ab", "an", "auf", "aus", "be", "bei", "da", "dar", "durch", "ein",
    "ent", "er", "fort", "gegen", "ge", "her", "hin", "hinter", "miss",
    "mit", "nach", "neben", "ob", "über", "um", "un", "unter", "ver",
    "vor", "weg", "wider", "wieder", "zer", "zu", "zwischen",
])


def _decompound_german(word: str) -> list[str]:
    """Split a German compound word into its constituent stems.

    Heuristic: try splitting at every position; accept splits where both parts
    are >= _MIN_PART_LEN and not trivial linker-only suffixes.
    Returns the original word plus all discovered parts.
    """
    parts = [word]
    w = word.lower()
    n = len(w)
    for i in range(_MIN_PART_LEN, n - _MIN_PART_LEN + 1):
        left = w[:i]
        right_raw = w[i:]
        # strip Fugenelement at the boundary
        for fuge in sorted(_FUGE, key=len, reverse=True):
            if right_raw.startswith(fuge) and len(right_raw) - len(fuge) >= _MIN_PART_LEN:
                right = right_raw[len(fuge):]
                if len(left) >= _MIN_PART_LEN and len(right) >= _MIN_PART_LEN:
                    parts.extend([left, right])
                break
        else:
            if len(right_raw) >= _MIN_PART_LEN:
                parts.append(right_raw)
    return parts


def tokenize(text: str, lang: str = "de") -> list[str]:
    """Tokenize text for BM25 indexing or query matching."""
    # Basic tokenization: split on non-alphanumeric, keep hyphens inside words
    tokens = re.findall(r"[a-zäöüßA-ZÄÖÜ0-9]+(?:-[a-zäöüßA-ZÄÖÜ0-9]+)*", text)
    tokens = [t.lower() for t in tokens]

    if lang == "de":
        stopws = _STOPWORDS_DE
        stemmer = _STEMMER_DE
        expanded: list[str] = []
        for t in tokens:
            if t in stopws:
                continue
            # Decompound then stem each part
            for part in _decompound_german(t):
                stemmed = stemmer.stem(part)
                if len(stemmed) >= 2 and stemmed not in stopws:
                    expanded.append(stemmed)
        return expanded
    else:
        stopws = _STOPWORDS_EN
        stemmer = _STEMMER_EN
        return [
            stemmer.stem(t) for t in tokens
            if t not in stopws and len(t) >= 2
        ]


# ── Vocabulary (built lazily per collection) ──────────────────────────────

class BM25Index:
    """Wraps BM25Okapi and exposes sparse-vector conversion for Qdrant."""

    def __init__(self, lang: str = "de"):
        """Initialize an empty index for the given language; call add_documents() before querying."""
        self.lang = lang
        self._vocab: dict[str, int] = {}
        self._corpus_tokens: list[list[str]] = []
        self._bm25: BM25Okapi | None = None

    def add_documents(self, texts: list[str]):
        """Tokenize texts, build vocabulary, and fit BM25Okapi on the corpus.

        Must be called before ``sparse_vector`` / ``query_sparse_vector``.
        Not incremental — rebuilding requires a new BM25Index instance.
        """
        for t in texts:
            toks = tokenize(t, self.lang)
            self._corpus_tokens.append(toks)
            for tok in toks:
                if tok not in self._vocab:
                    self._vocab[tok] = len(self._vocab)
        self._bm25 = BM25Okapi(self._corpus_tokens)

    def sparse_vector(self, text: str) -> dict[int, float]:
        """Return {token_index: bm25_score} for the given text."""
        if self._bm25 is None:
            return {}
        toks = tokenize(text, self.lang)
        scores: dict[int, float] = {}
        tok_freq: dict[str, int] = {}
        for t in toks:
            tok_freq[t] = tok_freq.get(t, 0) + 1
        for tok, freq in tok_freq.items():
            idx = self._vocab.get(tok)
            if idx is None:
                continue
            # BM25 term weight: use IDF * TF-normalized from rank_bm25 internals
            idf = self._bm25.idf.get(tok, 0.0)
            tf_norm = freq / (freq + self._bm25.k1 * (1 - self._bm25.b + self._bm25.b))
            scores[idx] = float(idf * tf_norm)
        return scores

    def query_sparse_vector(self, query: str) -> dict[int, float]:
        """Same as sparse_vector but only for tokens already in vocab."""
        return self.sparse_vector(query)

    def vocab_size(self) -> int:
        """Return the number of unique tokens in the vocabulary."""
        return len(self._vocab)
