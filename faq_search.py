"""Lightweight FAQ retrieval over data/fluxpark_faq_corpus.json.

This is the production-facing counterpart to scripts/finetune_faq_retriever.py:
that script's fine-tuned sentence-embedding model is a research artifact
(~470MB, needs torch) not suited to a deployed app. This module gives the
live AI assistant the same corpus, searched with a dependency-free scoring
function (stdlib only) so it stays cheap to deploy.

Plain Jaccard token overlap over-weights generic question words ("how",
"do", "i", "what", "does") that appear in nearly every FAQ entry, which was
enough to mismatch real queries during testing. Tokens are instead weighted
by inverse document frequency across the corpus, so distinctive content
words ("switch", "rent", "pending") drive the match far more than words
every question shares.
"""

import json
import math
import re
from functools import lru_cache
from pathlib import Path

CORPUS_PATH = Path(__file__).resolve().parent / "data" / "fluxpark_faq_corpus.json"
MATCH_THRESHOLD = 0.2
_WORD_RE = re.compile(r"\w+", re.UNICODE)


@lru_cache(maxsize=1)
def _load_corpus():
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def _stem(word: str) -> str:
    """Crude English plural-folding so "properties"/"property" and
    "slots"/"slot" count as the same token -- not a real stemmer, just
    enough to stop common plurals from costing a match."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("es"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _tokens(text: str) -> set:
    return {_stem(w) for w in _WORD_RE.findall(text.lower())}


@lru_cache(maxsize=8)
def _idf_weights(lang: str) -> dict:
    """Inverse document frequency of each token across this language's
    corpus questions: common words score low, distinctive words score high.
    """
    corpus = _load_corpus()
    doc_tokens = [_tokens(entry.get(f"question_{lang}", entry["question_en"])) for entry in corpus]
    n_docs = len(doc_tokens)
    doc_freq: dict = {}
    for tokens in doc_tokens:
        for token in tokens:
            doc_freq[token] = doc_freq.get(token, 0) + 1
    return {token: math.log(1 + n_docs / freq) for token, freq in doc_freq.items()}


def _weighted_overlap(query_tokens: set, candidate_tokens: set, weights: dict) -> float:
    if not query_tokens or not candidate_tokens:
        return 0.0
    default_weight = math.log(2)  # token unseen in the corpus: treat as moderately distinctive
    shared = query_tokens & candidate_tokens
    union = query_tokens | candidate_tokens
    shared_weight = sum(weights.get(t, default_weight) for t in shared)
    union_weight = sum(weights.get(t, default_weight) for t in union)
    return shared_weight / union_weight if union_weight else 0.0


def search_faq(query: str, lang: str = "en") -> dict | None:
    """Return the best-matching FAQ entry's question/answer in `lang`, or
    None if nothing in the corpus is a close enough match for the query.
    """
    weights = _idf_weights(lang)
    query_tokens = _tokens(query)

    best_score, best_entry = 0.0, None
    for entry in _load_corpus():
        candidate_tokens = _tokens(entry.get(f"question_{lang}", entry["question_en"]))
        score = _weighted_overlap(query_tokens, candidate_tokens, weights)
        if score > best_score:
            best_score, best_entry = score, entry

    if best_entry is None or best_score < MATCH_THRESHOLD:
        return None
    return {
        "question": best_entry.get(f"question_{lang}", best_entry["question_en"]),
        "answer": best_entry.get(f"answer_{lang}", best_entry["answer_en"]),
        "score": round(best_score, 3),
    }
