#!/usr/bin/env python3
"""Draft step: generate tailored artifacts for a posting.

Usage:
    python draft.py resume <posting_id>
    python draft.py briefing <posting_id>
    python draft.py cover-letter <posting_id>
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import anthropic
import yaml
from dotenv import load_dotenv

load_dotenv()  # pulls ANTHROPIC_API_KEY from a local .env file, if one exists

POSTINGS_DIR = Path(__file__).parent / "postings"
DRAFTS_DIR = Path(__file__).parent / "drafts"
RESUME_PATH = Path(__file__).parent / "data" / "resume.yaml"
STORIES_PATH = Path(__file__).parent / "data" / "stories.yaml"
VOICE_SAMPLES_PATH = Path(__file__).parent / "data" / "voice_samples.md"

REQUIRED_WEIGHT = 2
PREFERRED_WEIGHT = 1
TOP_STORIES_COUNT = 2

COVER_LETTER_MODEL = "claude-opus-5"
COVER_LETTER_SYSTEM_PROMPT = """\
You are helping a real candidate draft a cover letter for a real job application.

Ground every claim in the resume bullets, STAR stories, and detected posting requirements
given in the briefing below - never invent accomplishments, numbers, or experience that
aren't there. Where the candidate has a real gap against the posting's requirements, don't
call it out directly; instead lead with genuinely relevant strengths.

Match the tone, sentence rhythm, and vocabulary shown in the "writing voice" samples as
closely as you naturally can. Avoid generic AI-cover-letter phrasing ("I am excited to
apply", "I believe I would be a great fit", "I am confident that my skills align").

Keep it to 3-4 short paragraphs. Output ONLY the cover letter body text - no subject line,
no explanation of what you did, no markdown formatting.
"""


def load_yaml(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def load_posting_scope(posting_id: str) -> tuple[dict, set[str], set[str]]:
    """Load a posting and return (posting, required_skills, preferred_skills)."""
    posting_path = POSTINGS_DIR / f"{posting_id}.yaml"
    posting = load_yaml(posting_path)
    analysis = posting.get("analysis")
    if not analysis:
        raise ValueError(f"{posting_id} has not been analyzed yet - run analyze.py first")

    required = set(analysis["required_skills"])
    preferred = set(analysis["preferred_skills"])
    return posting, required, preferred


def bullet_score(tags: list[str], required: set[str], preferred: set[str]) -> int:
    score = 0
    for tag in tags:
        if tag in required:
            score += REQUIRED_WEIGHT
        elif tag in preferred:
            score += PREFERRED_WEIGHT
    return score


def tailor_bullets(bullets: list[dict], required: set[str], preferred: set[str]) -> list[dict]:
    """Highest-scoring bullets first. Python's sort is stable, so bullets with
    equal scores (including score 0) keep their original relative order."""
    return sorted(
        bullets,
        key=lambda b: -bullet_score(b.get("tags", []), required, preferred),
    )


def render_resume(resume: dict, required: set[str], preferred: set[str]) -> str:
    lines = []
    contact = resume["contact"]
    lines.append(f"# {contact['name']}")

    contact_bits = [contact.get("email"), contact.get("phone"), contact.get("location")]
    lines.append(" | ".join(bit for bit in contact_bits if bit))

    links = contact.get("links", [])
    if links:
        lines.append(" | ".join(f"[{l['label']}]({l['url']})" for l in links))
    lines.append("")

    if resume.get("summary"):
        lines.append("## Summary")
        lines.append(resume["summary"].strip())
        lines.append("")

    all_skills = resume.get("skills", [])
    matched_skills = [s for s in all_skills if s in required or s in preferred]
    other_skills = [s for s in all_skills if s not in matched_skills]
    lines.append("## Skills")
    lines.append(", ".join(matched_skills + other_skills))
    lines.append("")

    lines.append("## Experience")
    for job in resume.get("experience", []):
        end = job["end_date"] or "Present"
        lines.append(f"### {job['title']}, {job['company']} ({job['start_date']} – {end})")
        for bullet in tailor_bullets(job.get("bullets", []), required, preferred):
            lines.append(f"- {bullet['text']}")
        lines.append("")

    return "\n".join(lines)


def draft_resume(posting_id: str) -> Path:
    _, required, preferred = load_posting_scope(posting_id)
    resume = load_yaml(RESUME_PATH)

    markdown = render_resume(resume, required, preferred)

    DRAFTS_DIR.mkdir(exist_ok=True)
    out_path = DRAFTS_DIR / f"{posting_id}_resume.md"
    out_path.write_text(markdown)
    return out_path


def matched_tags(tags: list[str], required: set[str], preferred: set[str]) -> list[str]:
    """Which of a bullet's tags actually matched the posting, required first."""
    req = [t for t in tags if t in required]
    pref = [t for t in tags if t in preferred]
    return req + pref


def index_bullets_by_id(resume: dict) -> dict[str, dict]:
    """Flatten every bullet across every job into one {id: bullet} lookup."""
    index = {}
    for job in resume.get("experience", []):
        for bullet in job.get("bullets", []):
            index[bullet["id"]] = bullet
    return index


def top_bullets(resume: dict, required: set[str], preferred: set[str], n: int) -> list[dict]:
    all_bullets = [b for job in resume.get("experience", []) for b in job.get("bullets", [])]
    ranked = tailor_bullets(all_bullets, required, preferred)
    return [b for b in ranked if bullet_score(b.get("tags", []), required, preferred) > 0][:n]


def top_stories(stories_data: dict, bullets_by_id: dict[str, dict],
                 required: set[str], preferred: set[str], n: int) -> list[dict]:
    def story_score(story: dict) -> int:
        related = story.get("related_bullets", [])
        scores = [
            bullet_score(bullets_by_id[bid].get("tags", []), required, preferred)
            for bid in related if bid in bullets_by_id
        ]
        return max(scores, default=0)

    return sorted(stories_data.get("stories", []), key=lambda s: -story_score(s))[:n]


def render_briefing(posting: dict, resume: dict, stories_data: dict, voice_text: str,
                     required: set[str], preferred: set[str]) -> str:
    analysis = posting["analysis"]
    lines = [
        f"# Briefing: {posting['title']} at {posting['company']}",
        "",
        "Context for writing a cover letter - by hand, or pasted into an AI chat.",
        "",
        f"- Posting URL: {posting.get('url') or 'n/a'}",
        f"- Fit score: {analysis['fit_score']}",
        f"- Required skills detected: {', '.join(analysis['required_skills']) or 'none'}",
        f"- Preferred skills detected: {', '.join(analysis['preferred_skills']) or 'none'}",
        "",
        "## Gaps (acknowledge honestly, don't oversell)",
    ]
    for gap in analysis["gaps"]:
        lines.append(f"- {gap['skill']} ({gap['zone']}, your_level={gap['your_level']})")
    lines.append("")

    lines.append("## Most relevant resume bullets")
    for bullet in top_bullets(resume, required, preferred, n=4):
        matches = ", ".join(matched_tags(bullet.get("tags", []), required, preferred))
        lines.append(f"- {bullet['text']}  _(matches: {matches})_")
    lines.append("")

    lines.append("## Most relevant stories")
    bullets_by_id = index_bullets_by_id(resume)
    for story in top_stories(stories_data, bullets_by_id, required, preferred, n=TOP_STORIES_COUNT):
        lines.append(f"### {story['title']}")
        lines.append(f"- Situation: {story['situation'].strip()}")
        lines.append(f"- Task: {story['task'].strip()}")
        lines.append(f"- Action: {story['action'].strip()}")
        lines.append(f"- Result: {story['result'].strip()}")
        lines.append("")

    lines.append("## Your writing voice (reference, don't copy verbatim)")
    lines.append(voice_text.strip())
    lines.append("")

    return "\n".join(lines)


def draft_briefing(posting_id: str) -> Path:
    posting, required, preferred = load_posting_scope(posting_id)
    resume = load_yaml(RESUME_PATH)
    stories_data = load_yaml(STORIES_PATH)
    voice_text = VOICE_SAMPLES_PATH.read_text()

    markdown = render_briefing(posting, resume, stories_data, voice_text, required, preferred)

    DRAFTS_DIR.mkdir(exist_ok=True)
    out_path = DRAFTS_DIR / f"{posting_id}_briefing.md"
    out_path.write_text(markdown)
    return out_path


def generate_cover_letter_text(briefing_markdown: str) -> str:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Put it in a local .env file "
            "(ANTHROPIC_API_KEY=sk-ant-...) or export it in your shell."
        )

    client = anthropic.Anthropic()

    try:
        response = client.messages.create(
            model=COVER_LETTER_MODEL,
            max_tokens=2048,
            system=COVER_LETTER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": briefing_markdown}],
        )
    except anthropic.AuthenticationError:
        raise RuntimeError("ANTHROPIC_API_KEY was rejected - check that it's valid.")
    except anthropic.RateLimitError:
        raise RuntimeError("Rate limited by the Anthropic API - wait a bit and retry.")
    except anthropic.APIConnectionError:
        raise RuntimeError("Could not reach the Anthropic API - check your network connection.")
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Anthropic API error ({e.status_code}): {e.message}")

    return "".join(block.text for block in response.content if block.type == "text").strip()


def draft_cover_letter(posting_id: str) -> Path:
    posting, required, preferred = load_posting_scope(posting_id)
    resume = load_yaml(RESUME_PATH)
    stories_data = load_yaml(STORIES_PATH)
    voice_text = VOICE_SAMPLES_PATH.read_text()

    briefing_markdown = render_briefing(posting, resume, stories_data, voice_text, required, preferred)
    cover_letter = generate_cover_letter_text(briefing_markdown)

    DRAFTS_DIR.mkdir(exist_ok=True)
    out_path = DRAFTS_DIR / f"{posting_id}_cover_letter.md"
    out_path.write_text(cover_letter + "\n")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate tailored draft artifacts for a posting.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    resume_parser = subparsers.add_parser("resume", help="Generate a tailored resume variant")
    resume_parser.add_argument("posting", help="Posting id")

    briefing_parser = subparsers.add_parser("briefing", help="Generate a cover-letter briefing doc")
    briefing_parser.add_argument("posting", help="Posting id")

    cover_letter_parser = subparsers.add_parser("cover-letter", help="Generate a cover letter via the Claude API")
    cover_letter_parser.add_argument("posting", help="Posting id")

    args = parser.parse_args()

    try:
        if args.command == "resume":
            out_path = draft_resume(args.posting)
            print(f"Saved tailored resume to {out_path}")
        elif args.command == "briefing":
            out_path = draft_briefing(args.posting)
            print(f"Saved briefing to {out_path}")
        elif args.command == "cover-letter":
            out_path = draft_cover_letter(args.posting)
            print(f"Saved cover letter to {out_path}")
    except (ValueError, RuntimeError) as e:
        # Expected, actionable failures (missing analysis, missing API key, API
        # errors) - show just the message. Anything else is a real bug, so let
        # it raise with a full traceback instead of being silently downgraded.
        raise SystemExit(f"Error: {e}")


if __name__ == "__main__":
    main()
