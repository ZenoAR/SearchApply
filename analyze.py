#!/usr/bin/env python3
"""Analyze a posting: extract skill mentions, diff against skills.yaml, compute fit_score.

Usage:
    python analyze.py <posting_id>
    python analyze.py postings/foo-corp-backend-engineer-fe9ff3.yaml
"""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

import yaml

POSTINGS_DIR = Path(__file__).parent / "postings"
SKILLS_PATH = Path(__file__).parent / "data" / "skills.yaml"
VOCAB_PATH = Path(__file__).parent / "data" / "skill_vocabulary.yaml"

REQUIRED_TRIGGERS = re.compile(
    r"\b(required|require|must have|minimum qualifications|requirements)\b", re.I
)
PREFERRED_TRIGGERS = re.compile(
    r"\b(preferred|nice to have|bonus|plus|desired)\b", re.I
)

LEVEL_RANK = {"none": 0, "learning": 1, "comfortable": 2, "confident": 3}
STRONG_LEVELS = {"comfortable", "confident"}
ZONE_WEIGHT = {"required": 2, "preferred": 1}


def load_yaml(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def load_my_skills() -> dict[str, str]:
    """name -> level, from data/skills.yaml"""
    data = load_yaml(SKILLS_PATH)
    return {s["name"]: s["level"] for s in data["skills"]}


def build_matchers(vocab_path: Path = VOCAB_PATH) -> list[tuple[str, re.Pattern]]:
    """Return [(canonical_name, compiled_regex), ...] - one regex per skill that
    matches the canonical name OR any of its aliases, whole-word, case-insensitive."""
    data = load_yaml(vocab_path)
    matchers = []
    for skill in data["skills"]:
        variants = [skill["name"]] + skill.get("aliases", [])
        pattern = r"\b(" + "|".join(re.escape(v) for v in variants) + r")\b"
        matchers.append((skill["name"], re.compile(pattern, re.I)))
    return matchers


def extract_mentions(raw_text: str, matchers: list[tuple[str, re.Pattern]]) -> dict[str, str]:
    """Scan raw_text line by line, tracking required/preferred zone.
    Returns {skill_name: zone}. If a skill appears in both zones, 'required' wins."""
    mentions: dict[str, str] = {}
    zone = "required"
    for line in raw_text.splitlines():
        if REQUIRED_TRIGGERS.search(line):
            zone = "required"
        elif PREFERRED_TRIGGERS.search(line):
            zone = "preferred"

        for skill_name, pattern in matchers:
            if pattern.search(line):
                if mentions.get(skill_name) != "required":
                    mentions[skill_name] = zone

    return mentions


def compute_fit_score(mentions: dict[str, str], my_skills: dict[str, str]) -> float:
    if not mentions:
        return 0.0

    earned = 0
    total = 0
    for skill_name, zone in mentions.items():
        weight = ZONE_WEIGHT[zone]
        total += weight
        level = my_skills.get(skill_name, "none")
        if level in STRONG_LEVELS:
            earned += weight

    return round(earned / total, 2)


def compute_gaps(mentions: dict[str, str], my_skills: dict[str, str]) -> list[dict]:
    gaps = []
    for skill_name, zone in mentions.items():
        level = my_skills.get(skill_name, "none")
        if level not in STRONG_LEVELS:
            gaps.append({"skill": skill_name, "zone": zone, "your_level": level})

    gaps.sort(key=lambda g: (g["zone"] != "required", LEVEL_RANK[g["your_level"]]))
    return gaps


def analyze_posting(posting_path: Path) -> dict:
    posting = load_yaml(posting_path)
    my_skills = load_my_skills()
    matchers = build_matchers()

    mentions = extract_mentions(posting["raw_text"], matchers)
    required_skills = sorted(s for s, z in mentions.items() if z == "required")
    preferred_skills = sorted(s for s, z in mentions.items() if z == "preferred")

    analysis = {
        "required_skills": required_skills,
        "preferred_skills": preferred_skills,
        "gaps": compute_gaps(mentions, my_skills),
        "fit_score": compute_fit_score(mentions, my_skills),
        "analyzed_at": date.today().isoformat(),
    }

    posting["analysis"] = analysis
    with posting_path.open("w") as f:
        yaml.safe_dump(posting, f, sort_keys=False, allow_unicode=True, width=100)

    return analysis


def resolve_posting_path(posting_id_or_path: str) -> Path:
    candidate = Path(posting_id_or_path)
    if candidate.exists():
        return candidate
    return POSTINGS_DIR / f"{posting_id_or_path}.yaml"


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a posting against skills.yaml.")
    parser.add_argument("posting", help="Posting id (e.g. foo-corp-backend-engineer-fe9ff3) or file path")
    args = parser.parse_args()

    posting_path = resolve_posting_path(args.posting)
    analysis = analyze_posting(posting_path)

    print(f"fit_score: {analysis['fit_score']}")
    print(f"required_skills: {analysis['required_skills']}")
    print(f"preferred_skills: {analysis['preferred_skills']}")
    print("gaps (priority order):")
    for gap in analysis["gaps"]:
        print(f"  - {gap['skill']} ({gap['zone']}, your_level={gap['your_level']})")


if __name__ == "__main__":
    main()
