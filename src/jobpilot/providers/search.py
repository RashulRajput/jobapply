from __future__ import annotations

from typing import Dict, List

import requests
from bs4 import BeautifulSoup

from jobpilot.models import JobPosting


ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
REMOTEOK_URL = "https://remoteok.com/api"


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "JobPilot/0.1 (+local resume-driven job automation)",
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        }
    )
    return session


def _html_to_text(value: str) -> str:
    return BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)


def _from_arbeitnow(item: Dict[str, object], page_number: int) -> JobPosting:
    title = str(item.get("title", ""))
    slug = str(item.get("slug", title.lower().replace(" ", "-")))
    location = str(item.get("location", ""))
    remote = "remote" in location.lower() or bool(item.get("remote"))
    return JobPosting(
        id=f"arbeitnow-{page_number}-{slug}",
        title=title,
        company=str(item.get("company_name", "")),
        location=location,
        description=_html_to_text(str(item.get("description", ""))),
        url=str(item.get("url", "")),
        apply_url=str(item.get("url", "")),
        source="arbeitnow",
        remote=remote,
        tags=[str(tag) for tag in item.get("tags", []) if tag],
        published_at=str(item.get("created_at", "")),
    )


def _from_remoteok(item: Dict[str, object]) -> JobPosting | None:
    title = str(item.get("position", "") or item.get("title", ""))
    if not title:
        return None
    tags = [str(tag) for tag in item.get("tags", []) if tag]
    description = _html_to_text(str(item.get("description", "")))
    location = str(item.get("location", "Remote"))
    url = str(item.get("url", item.get("apply_url", "")))
    remote = "remote" in location.lower() or bool(item.get("remote"))
    identifier = str(item.get("id", title.lower().replace(" ", "-")))
    return JobPosting(
        id=f"remoteok-{identifier}",
        title=title,
        company=str(item.get("company", "")),
        location=location,
        description=description,
        url=url,
        apply_url=url,
        source="remoteok",
        remote=remote,
        tags=tags,
        published_at=str(item.get("date", "")),
    )


def fetch_arbeitnow_jobs(search_config: Dict[str, object]) -> List[JobPosting]:
    pages = int(search_config.get("arbeitnow_pages", 2))
    jobs: List[JobPosting] = []
    session = _session()
    for page_number in range(1, pages + 1):
        response = session.get(ARBEITNOW_URL, params={"page": page_number}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        for item in payload.get("data", []):
            jobs.append(_from_arbeitnow(item, page_number))
    return jobs


def fetch_remoteok_jobs() -> List[JobPosting]:
    session = _session()
    response = session.get(REMOTEOK_URL, timeout=30)
    response.raise_for_status()
    payload = response.json()
    jobs: List[JobPosting] = []
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            job = _from_remoteok(item)
            if job:
                jobs.append(job)
    return jobs


def fetch_jobs(search_config: Dict[str, object]) -> List[JobPosting]:
    providers = {str(item).lower() for item in search_config.get("providers", [])}
    jobs: List[JobPosting] = []
    errors: List[str] = []

    if "arbeitnow" in providers:
        try:
            jobs.extend(fetch_arbeitnow_jobs(search_config))
        except Exception as exc:
            errors.append(f"arbeitnow failed: {exc}")

    if "remoteok" in providers:
        try:
            jobs.extend(fetch_remoteok_jobs())
        except Exception as exc:
            errors.append(f"remoteok failed: {exc}")

    unique: Dict[str, JobPosting] = {}
    for job in jobs:
        key = job.apply_url or job.url or job.id
        unique[key] = job

    if errors:
        print("Provider warnings:")
        for error in errors:
            print(f"  - {error}")

    return list(unique.values())
