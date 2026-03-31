from __future__ import annotations

import argparse
import json
from typing import Any

from jobpilot.config import load_config
from jobpilot.workflow import build_profile, run_pipeline, search_jobs, watch_inbox


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resume-driven job search and application bot.")
    parser.add_argument("--config", default="config/jobpilot.json", help="Path to the bot config file.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("profile", help="Print the inferred candidate profile.")

    search_parser = subparsers.add_parser("search", help="Fetch and rank jobs without applying.")
    search_parser.add_argument("--limit", type=int, default=15, help="Maximum number of jobs to print.")

    run_parser = subparsers.add_parser("run", help="Fetch, rank, and apply to jobs.")
    run_parser.add_argument("--limit", type=int, default=10, help="Maximum number of jobs to evaluate.")
    run_parser.add_argument(
        "--no-apply",
        action="store_true",
        help="Disable auto-apply for this run.",
    )

    subparsers.add_parser("watch-inbox", help="Scan Gmail for interview-related emails.")
    return parser


def _print_jobs(jobs: list[Any]) -> None:
    if not jobs:
        print("No jobs matched the current score threshold.")
        return
    for index, job in enumerate(jobs, start=1):
        print(f"{index:02d}. [{job.score:>5}] {job.company} | {job.title} | {job.location}")
        print(f"    {job.url}")
        if job.fit_notes:
            print(f"    {'; '.join(job.fit_notes)}")


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    config = load_config(args.config)

    if args.command == "profile":
        profile = build_profile(config)
        print(json.dumps(profile.to_dict(), indent=2, ensure_ascii=False))
        return 0

    if args.command == "search":
        ranked = search_jobs(config, limit=args.limit)
        _print_jobs(ranked[: args.limit])
        return 0

    if args.command == "run":
        output = run_pipeline(
            config,
            limit=args.limit,
            auto_apply=not args.no_apply,
        )
        _print_jobs(output["ranked_jobs"][: args.limit])
        if output["application_results"]:
            print("\nApplication results:")
            for result in output["application_results"]:
                print(f"- {result.company} | {result.title} | {result.status} | {result.detail}")
        else:
            print("\nNo applications were submitted in this run.")
        return 0

    if args.command == "watch-inbox":
        matches = watch_inbox(config)
        if not matches:
            print("No interview-style emails found, or Gmail credentials are not configured yet.")
            return 0
        for item in matches:
            print(f"- {item['date']} | {item['from']} | {item['subject']}")
            print(f"  {item['snippet']}")
        return 0

    parser.print_help()
    return 1
