from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List


@dataclass
class CandidateProfile:
    full_name: str
    email: str
    phone: str
    location: str
    summary: str
    current_title: str = ""
    years_experience: float | None = None
    target_titles: List[str] = field(default_factory=list)
    preferred_locations: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    education: List[str] = field(default_factory=list)
    links: Dict[str, str] = field(default_factory=dict)
    custom_answers: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class JobPosting:
    id: str
    title: str
    company: str
    location: str
    description: str
    url: str
    apply_url: str
    source: str
    remote: bool = False
    tags: List[str] = field(default_factory=list)
    published_at: str = ""
    score: float = 0.0
    matched_keywords: List[str] = field(default_factory=list)
    fit_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class ApplicationResult:
    job_id: str
    company: str
    title: str
    url: str
    status: str
    detail: str = ""
    contact_emails: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)
