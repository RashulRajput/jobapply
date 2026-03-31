from __future__ import annotations

from typing import Dict, Iterable, List

from jobpilot.models import CandidateProfile, JobPosting


ENTRY_LEVEL_HINTS = {
    "entry level",
    "entry-level",
    "junior",
    "graduate",
    "new grad",
    "associate",
    "trainee",
    "fresher",
}

SENIORITY_BLOCKERS = {
    "senior",
    "staff",
    "lead",
    "principal",
    "manager",
    "architect",
    "director",
    "head of",
}


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _contains_any(text: str, values: Iterable[str]) -> bool:
    return any(value.lower() in text for value in values)


def score_job(job: JobPosting, profile: CandidateProfile, search_config: Dict[str, object]) -> JobPosting:
    searchable = _normalize(
        " ".join(
            [
                job.title,
                job.company,
                job.location,
                job.description,
                " ".join(job.tags),
            ]
        )
    )
    normalized_title = _normalize(job.title)
    target_titles = [str(item).lower() for item in search_config.get("target_titles", [])]
    preferred_locations = [str(item).lower() for item in profile.preferred_locations]
    keywords = [keyword.lower() for keyword in profile.keywords]

    matched_keywords = [keyword for keyword in keywords if keyword and keyword in searchable]
    title_score = 30 if _contains_any(normalized_title, target_titles) else 0
    keyword_score = min(45, len(matched_keywords) * 5)

    location_match = job.remote or any(location in searchable for location in preferred_locations)
    location_score = 0
    if job.remote:
        location_score += 12
    elif location_match:
        location_score += 10
    elif preferred_locations:
        location_score -= 25

    entry_level_score = 8 if _contains_any(searchable, ENTRY_LEVEL_HINTS) else 0
    seniority_penalty = 40 if _contains_any(normalized_title, SENIORITY_BLOCKERS) else 0

    if profile.years_experience is not None and profile.years_experience <= 3:
        experience_fit = 5 if not seniority_penalty else -10
    else:
        experience_fit = 0

    score = max(0.0, min(100.0, title_score + keyword_score + location_score + entry_level_score + experience_fit - seniority_penalty))
    fit_notes: List[str] = []
    if matched_keywords:
        fit_notes.append(f"Matched keywords: {', '.join(matched_keywords[:8])}")
    if job.remote:
        fit_notes.append("Remote-friendly listing")
    elif location_match:
        fit_notes.append("Location matches your preferred geography")
    if _contains_any(searchable, ENTRY_LEVEL_HINTS):
        fit_notes.append("Entry-level phrasing detected")
    if seniority_penalty:
        fit_notes.append("Looks more senior than your current target")
    if preferred_locations and not location_match:
        fit_notes.append("Outside your preferred locations")

    job.score = round(score, 1)
    job.matched_keywords = matched_keywords[:12]
    job.fit_notes = fit_notes
    return job


def rank_jobs(
    jobs: List[JobPosting],
    profile: CandidateProfile,
    search_config: Dict[str, object],
) -> List[JobPosting]:
    scored = [score_job(job, profile, search_config) for job in jobs]
    minimum_score = float(search_config.get("minimum_score", 55))
    shortlisted = [job for job in scored if job.score >= minimum_score]
    shortlisted.sort(key=lambda item: item.score, reverse=True)
    return shortlisted
