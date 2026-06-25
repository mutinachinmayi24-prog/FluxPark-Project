"""Export data/fluxpark_faq_corpus.json into one plain-text file per language,
ready to hand to the Swecha Corpus Client CLI (`corpus-client upload-files`).

This only prepares files on disk -- it does not log in or upload anything.
See scripts/README.md for the manual steps (login requires your own Swecha
account credentials).
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CORPUS_PATH = DATA_DIR / "fluxpark_faq_corpus.json"
OUT_DIR = Path(__file__).resolve().parent.parent / "corpus-export"

LANGS = {"en": "English", "hi": "Hindi", "te": "Telugu"}


def main():
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(exist_ok=True)

    for lang in LANGS:
        lines = []
        for entry in corpus:
            lines.append(f"Q: {entry[f'question_{lang}']}")
            lines.append(f"A: {entry[f'answer_{lang}']}")
            lines.append("")
        out_path = OUT_DIR / f"fluxpark_faq_{lang}.txt"
        out_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"Wrote {out_path} ({len(corpus)} Q&A pairs, {LANGS[lang]})")


if __name__ == "__main__":
    main()
