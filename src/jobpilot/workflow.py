from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from jobpilot.application import apply_to_jobs
from jobpilot.config import load_json, save_json, utc_timestamp
from jobpilot.matching import rank_jobs
from jobpilot.models import ApplicationResult, CandidateProfile, JobPosting
from jobpilot.notifications import build_hr_email, scan_inbox_for_interviews, send_email_message
from jobpilot.providers import fetch_jobs
from jobpilot.resume import apply_profile_overrides, extract_resume_text, parse_candidate_profile


def _state_path(config: Dict[str, Any]) -> Path:
    return Path(config["project_root"]) / "data" / "state.json"


def _matches_path(config: Dict[str, Any]) -> Path:
    return Path(config["project_root"]) / "data" / "latest_matches.json"


def _applications_path(config: Dict[str, Any]) -> Path:
    return Path(config["project_root"]) / "data" / "latest_applications.json"


def load_state(config: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    return load_json(
        _state_path(config),
        {
            "seen_jobs": {},
            "applied_jobs": {},
            "emailed_contacts": {},
        },
    )


def save_state(config: Dict[str, Any], state: Dict[str, Dict[str, str]]) -> None:
    save_json(_state_path(config), state)


def build_profile(config: Dict[str, Any]) -> CandidateProfile:
    text = extract_resume_text(config["resume_path"])
    profile = parse_candidate_profile(text)
    return apply_profile_overrides(profile, config.get("profile_overrides", {}))


def search_jobs(config: Dict[str, Any], limit: int | None = None) -> List[JobPosting]:
    profile = build_profile(config)
    jobs = fetch_jobs(config["search"])
    ranked = rank_jobs(jobs, profile, config["search"])
    if limit is not None:
        ranked = ranked[:limit]

    save_json(_matches_path(config), [job.to_dict() for job in ranked])
    return ranked


def _new_jobs_only(jobs: List[JobPosting], state: Dict[str, Dict[str, str]]) -> List[JobPosting]:
    applied = state.get("applied_jobs", {})
    return [job for job in jobs if (job.apply_url or job.url) not in applied]


def _mark_seen_jobs(jobs: List[JobPosting], state: Dict[str, Dict[str, str]]) -> None:
    seen = state.setdefault("seen_jobs", {})
    for job in jobs:
        seen[job.apply_url or job.url] = utc_timestamp()


def _mark_applied(results: List[ApplicationResult], state: Dict[str, Dict[str, str]]) -> None:
    applied = state.setdefault("applied_jobs", {})
    for result in results:
        if result.status in {"submitted", "submitted_unconfirmed"}:
            applied[result.url] = utc_timestamp()


def _send_hr_outreach(
    results: List[ApplicationResult],
    profile: CandidateProfile,
    jobs_by_url: Dict[str, JobPosting],
    config: Dict[str, Any],
    state: Dict[str, Dict[str, str]],
) -> None:
    email_config = config.get("email", {})
    if not email_config.get("enabled") or not email_config.get("send_hr_outreach"):
        return

    emailed = state.setdefault("emailed_contacts", {})
    for result in results:
        if result.status not in {"submitted", "submitted_unconfirmed"}:
            continue
        for email_address in result.contact_emails:
            key = f"{result.url}|{email_address}"
            if key in emailed:
                continue
            job = jobs_by_url.get(result.url)
            if not job:
                continue
            message = build_hr_email(profile, job)
            try:
                send_email_message(
                    email_config,
                    message,
                    [email_address],
                    resume_path=config["resume_path"],
                )
            except Exception as exc:
                print(f"HR outreach skipped for {email_address}: {exc}")
                continue
            emailed[key] = utc_timestamp()


def run_pipeline(
    config: Dict[str, Any],
    limit: int | None = None,
    auto_apply: bool | None = None,
) -> Dict[str, Any]:
    profile = build_profile(config)
    ranked = search_jobs(config, limit=limit)
    state = load_state(config)
    _mark_seen_jobs(ranked, state)

    apply_enabled = config.get("application", {}).get("auto_apply", True) if auto_apply is None else auto_apply
    apply_threshold = float(config["search"].get("apply_threshold", 70))
    candidates = [job for job in ranked if job.score >= apply_threshold]
    new_candidates = _new_jobs_only(candidates, state)

    results: List[ApplicationResult] = []
    if apply_enabled and new_candidates:
        results = apply_to_jobs(new_candidates, profile, config["application"])
        save_json(_applications_path(config), [item.to_dict() for item in results])
        _mark_applied(results, state)
        jobs_by_url = {job.apply_url or job.url: job for job in new_candidates}
        _send_hr_outreach(results, profile, jobs_by_url, config, state)

    save_state(config, state)
    return {
        "profile": profile,
        "ranked_jobs": ranked,
        "application_results": results,
    }


def watch_inbox(config: Dict[str, Any]) -> List[Dict[str, str]]:
    return scan_inbox_for_interviews(config.get("email", {}))
