"""Fine-tune a multilingual sentence embedding model on FluxPark's own FAQ
corpus (data/fluxpark_faq_corpus.json) for cross-lingual FAQ retrieval, and
report retrieval accuracy before/after on a held-out paraphrase set
(data/fluxpark_faq_eval.json).

This is a genuine, runnable fine-tune (real gradient updates on real data),
scoped deliberately small: a 118M-parameter sentence embedding model, ~75
training pairs, a handful of epochs. It trains in a couple of minutes on CPU
-- there is no GPU in this environment, so a full LLM fine-tune is not
attempted here; this is the proof-of-concept that fits the hardware.

Requires the optional ML extras (not part of requirements.txt/requirements-
dev.txt, since the app itself doesn't need them):

    pip install sentence-transformers torch

Usage:
    python scripts/finetune_faq_retriever.py
"""

import json
from pathlib import Path

from sentence_transformers import InputExample, SentenceTransformer, losses
from torch.utils.data import DataLoader

BASE_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CORPUS_PATH = DATA_DIR / "fluxpark_faq_corpus.json"
EVAL_PATH = DATA_DIR / "fluxpark_faq_eval.json"
MODEL_OUT_DIR = Path(__file__).resolve().parent.parent / "models" / "fluxpark-faq-retriever"
REPORT_PATH = DATA_DIR / "fluxpark_faq_finetune_report.json"

LANGS = ("en", "hi", "te")


def load_corpus():
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def load_eval_set():
    return json.loads(EVAL_PATH.read_text(encoding="utf-8"))


def build_index(corpus):
    """One indexed document per (entry, language): (text, faq_id)."""
    texts, ids = [], []
    for entry in corpus:
        for lang in LANGS:
            texts.append(entry[f"question_{lang}"])
            ids.append(entry["id"])
    return texts, ids


def evaluate_retrieval(model, index_texts, index_ids, eval_set):
    """Accuracy@1: does the nearest indexed question share the query's FAQ id?"""
    index_embeddings = model.encode(index_texts, normalize_embeddings=True)
    query_texts = [item["query"] for item in eval_set]
    query_embeddings = model.encode(query_texts, normalize_embeddings=True)

    correct = 0
    per_item = []
    for item, query_embedding in zip(eval_set, query_embeddings, strict=True):
        scores = query_embedding @ index_embeddings.T
        best = int(scores.argmax())
        predicted_id = index_ids[best]
        is_correct = predicted_id == item["id"]
        correct += int(is_correct)
        per_item.append(
            {
                "query": item["query"],
                "lang": item["lang"],
                "expected_id": item["id"],
                "predicted_id": predicted_id,
                "correct": is_correct,
            }
        )
    accuracy = correct / len(eval_set)
    return accuracy, per_item


def build_training_pairs(corpus):
    """Cross-lingual positive pairs: every language pair of the same FAQ
    entry's question becomes an anchor/positive example, teaching the model
    that question variants of the same id (in any of the 3 languages) should
    embed close together. In-batch negatives (other ids) come for free from
    MultipleNegativesRankingLoss.
    """
    examples = []
    for entry in corpus:
        for i, lang_a in enumerate(LANGS):
            for lang_b in LANGS[i + 1 :]:
                examples.append(
                    InputExample(texts=[entry[f"question_{lang_a}"], entry[f"question_{lang_b}"]])
                )
    return examples


def main():
    corpus = load_corpus()
    eval_set = load_eval_set()
    index_texts, index_ids = build_index(corpus)

    print(
        f"Corpus: {len(corpus)} FAQ entries x {len(LANGS)} languages = {len(index_texts)} indexed questions"
    )
    print(f"Held-out eval set: {len(eval_set)} queries\n")

    print(f"Loading baseline model: {BASE_MODEL}")
    model = SentenceTransformer(BASE_MODEL)

    print("Evaluating baseline (before fine-tuning)...")
    baseline_accuracy, baseline_detail = evaluate_retrieval(model, index_texts, index_ids, eval_set)
    print(f"Baseline accuracy@1: {baseline_accuracy:.1%}\n")

    training_pairs = build_training_pairs(corpus)
    print(f"Fine-tuning on {len(training_pairs)} cross-lingual positive pairs...")
    train_dataloader = DataLoader(training_pairs, shuffle=True, batch_size=16)
    train_loss = losses.MultipleNegativesRankingLoss(model)
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=8,
        warmup_steps=10,
        show_progress_bar=False,
    )

    print("\nEvaluating fine-tuned model...")
    tuned_accuracy, tuned_detail = evaluate_retrieval(model, index_texts, index_ids, eval_set)
    print(f"Fine-tuned accuracy@1: {tuned_accuracy:.1%}\n")

    MODEL_OUT_DIR.parent.mkdir(exist_ok=True)
    model.save(str(MODEL_OUT_DIR))
    print(
        f"Saved fine-tuned model to {MODEL_OUT_DIR} (not committed to git -- see scripts/README.md)"
    )

    report = {
        "base_model": BASE_MODEL,
        "corpus_size": len(corpus),
        "indexed_questions": len(index_texts),
        "training_pairs": len(training_pairs),
        "eval_queries": len(eval_set),
        "baseline_accuracy_at_1": baseline_accuracy,
        "finetuned_accuracy_at_1": tuned_accuracy,
        "baseline_detail": baseline_detail,
        "finetuned_detail": tuned_detail,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote metrics report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
