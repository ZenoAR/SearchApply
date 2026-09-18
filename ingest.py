#!/usr/bin/env python3
"""Ingest a manually-pasted job posting into postings/<id>.yaml.

Usage:
    python ingest.py --company "Foo Corp" --title "Backend Engineer" --url "https://..." < posting.txt
    python ingest.py --company "Foo Corp" --title "Backend Engineer" --file posting.txt
    python ingest.py --company "Foo Corp" --title "Backend Engineer"   # then paste, then Ctrl-D
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import date
from pathlib import Path

import yaml

POSTINGS_DIR = Path(__file__).parent / "postings"


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def make_posting_id(company: str, title: str, raw_text: str) -> str:
    digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()[:6]
    return f"{slugify(company)}-{slugify(title)}-{digest}"


def ingest(company: str, title: str, raw_text: str, url: str | None = None) -> Path:
    raw_text = raw_text.strip()
    if not raw_text:
        raise ValueError("raw_text is empty - nothing to ingest")

    posting_id = make_posting_id(company, title, raw_text)
    posting = {
        "id": posting_id,
        "company": company,
        "title": title,
        "url": url,
        "source": "manual",
        "date_added": date.today().isoformat(),
        "raw_text": raw_text,
        "analysis": None,  # filled in by the `analyze` step
    }

    POSTINGS_DIR.mkdir(exist_ok=True)
    out_path = POSTINGS_DIR / f"{posting_id}.yaml"
    with out_path.open("w") as f:
        yaml.safe_dump(posting, f, sort_keys=False, allow_unicode=True, width=100)

    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a manually-pasted job posting.")
    parser.add_argument("--company", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--url", default=None)
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Path to a text file containing the posting body. If omitted, reads from stdin.",
    )
    args = parser.parse_args()

    if args.file:
        raw_text = args.file.read_text()
    else:
        print("Paste the job posting text, then press Ctrl-D when done:", file=sys.stderr)
        raw_text = sys.stdin.read()

    out_path = ingest(args.company, args.title, raw_text, args.url)
    print(f"Saved posting to {out_path}")


if __name__ == "__main__":
    main()
