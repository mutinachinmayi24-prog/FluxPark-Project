# ML / corpus scripts

These are standalone scripts outside the main app — they're not imported by
`main.py`, not covered by `requirements.txt`/`requirements-dev.txt`, and not
run in CI. Install their extra dependencies yourself before running them.

## `finetune_faq_retriever.py` — FAQ retrieval fine-tuning

Fine-tunes a small multilingual sentence-embedding model
(`paraphrase-multilingual-MiniLM-L12-v2`, 118M params) on FluxPark's own FAQ
corpus (`data/fluxpark_faq_corpus.json`, 25 question/answer pairs in
English/Hindi/Telugu) so that a question asked in any of the three languages
retrieves the right FAQ entry, even if it's phrased differently from the
stored version.

This is a genuine, small-scale fine-tune chosen to match the hardware
actually available: there's no GPU in this environment (only an integrated
AMD GPU, no CUDA/ROCm), so a full LLM fine-tune isn't realistic in CI/dev
time. A 118M-parameter embedding model on ~75 training pairs trains in
under two minutes on CPU and produces a real, measurable result.

**Result (2026-06-26):**

| | Accuracy@1 on 30 held-out paraphrased queries |
|---|---|
| Baseline (`paraphrase-multilingual-MiniLM-L12-v2`, off the shelf) | 63.3% |
| Fine-tuned on FluxPark's FAQ corpus | 73.3% |

Full per-query predictions are in `data/fluxpark_faq_finetune_report.json`.

```bash
pip install sentence-transformers torch datasets accelerate
python scripts/finetune_faq_retriever.py
```

The fine-tuned model is written to `models/fluxpark-faq-retriever/` (~470MB,
git-ignored — regenerate it with the command above rather than committing
binary weights).

## `export_corpus_for_upload.py` — Corpus CLI export

Exports the same FAQ corpus into one plain-text file per language under
`corpus-export/`, in a form ready to hand to Swecha's
[Corpus Client CLI](https://code.swecha.org/corpus/corpus-client-cli)
(`corpus-client`).

```bash
python scripts/export_corpus_for_upload.py
```

**Uploading is a manual, one-time step you run yourself** — it needs your own
Swecha account (phone number + password), which this script never has access
to:

```bash
# install (Python 3.14+, requires uv or pipx)
uv tool install git+https://code.swecha.org/corpus/corpus-client-cli

# login with your own Swecha account
corpus-client login

# find the right category id for text/document content
corpus-client categories

# fill in category_ids / release_rights / creator in
# corpus-export/upload_metadata.csv, then:
corpus-client upload-files --csv corpus-export/upload_metadata.csv
```

`corpus-client languages` confirms `en`, `hi`, and `te` are all supported
language codes on the platform.

## `browser_smoke_test.js` — cross-engine browser compatibility check

Loads `/signup` in Chromium, Firefox, and WebKit (the actual rendering
engines behind Chrome/Edge, Firefox, and Safari respectively), and checks
the HTTP status, console errors, and service worker registration in each.
Real Safari isn't installable on Windows, so WebKit is the closest available
proxy — it's genuinely Safari's engine, just not Apple's exact browser build.

```bash
npm install playwright
npx playwright install chromium firefox webkit
uvicorn main:app --host 127.0.0.1 --port 8000 &
node scripts/browser_smoke_test.js http://127.0.0.1:8000
```

**Result (2026-06-26):** all three engines passed — HTTP 200, zero console
errors, service worker registered successfully in each.
