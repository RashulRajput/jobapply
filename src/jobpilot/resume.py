from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from pypdf import PdfReader

from jobpilot.models import CandidateProfile


KNOWN_HEADINGS = {
    "OBJECTIVE",
    "EDUCATION",
    "EXPERIENCE",
    "PROJECTS",
    "SKILLS",
    "LEADERSHIP & COMMUNITY",
}

KNOWN_KEYWORDS = [
    "python",
    "react",
    "typescript",
    "node.js",
    "javascript",
    "fastapi",
    "flask",
    "supabase",
    "postgresql",
    "sql",
    "docker",
    "aws",
    "ec2",
    "openai",
    "llm",
    "langchain",
    "selenium",
    "web scraping",
    "beautifulsoup",
    "api integration",
    "data analysis",
    "data pipelines",
    "machine learning",
    "tensorflow",
    "keras",
    "numpy",
    "scipy",
    "golang",
    "node",
    "iot",
]


def _dedupe(items: List[str]) -> List[str]:
    seen: set[str] = set()
    unique: List[str] = []
    for item in items:
        cleaned = item.strip()
        lowered = cleaned.lower()
        if cleaned and lowered not in seen:
            seen.add(lowered)
            unique.append(cleaned)
    return unique


def _extract_text_with_pypdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def _extract_text_with_pdftotext(path: Path) -> str:
    candidates = [
        Path(os.environ.get("PDFTOTEXT_PATH", "")),
        Path(r"C:\Users\DELL\AppData\Local\Programs\MiKTeX\miktex\bin\x64\pdftotext.exe"),
    ]
    for executable in candidates:
        if not executable or not executable.exists():
            continue
        result = subprocess.run(
            [str(executable), "-layout", str(path), "-"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.stdout.strip():
            return result.stdout.strip()
    return ""


def extract_resume_text(path: str | Path) -> str:
    resume_path = Path(path).resolve()
    suffix = resume_path.suffix.lower()
    if suffix == ".pdf":
        text = _extract_text_with_pypdf(resume_path)
        if text.strip():
            return text
        text = _extract_text_with_pdftotext(resume_path)
        if text.strip():
            return text
        raise ValueError(f"Could not extract text from PDF: {resume_path}")
    if suffix in {".txt", ".md"}:
        return resume_path.read_text(encoding="utf-8")
    raise ValueError(f"Unsupported resume type: {resume_path.suffix}")


def split_sections(text: str) -> Dict[str, str]:
    sections: Dict[str, List[str]] = {"HEADER": []}
    current = "HEADER"
    for raw_line in text.splitlines():
        line = raw_line.strip()
        heading = line.upper()
        if heading in KNOWN_HEADINGS:
            current = heading
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(raw_line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def _extract_email(text: str) -> str:
    match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return match.group(0) if match else ""


def _extract_phone(text: str) -> str:
    match = re.search(r"(?:\+?\d[\d\s-]{8,}\d)", text)
    return match.group(0).strip() if match else ""


def _extract_header_lines(header: str) -> List[str]:
    return [line.strip() for line in header.splitlines() if line.strip()]


def _extract_name(header: str) -> str:
    lines = _extract_header_lines(header)
    return lines[0] if lines else ""


def _extract_location(header: str) -> str:
    lines = _extract_header_lines(header)
    if len(lines) >= 2 and "|" in lines[1]:
        return lines[1].split("|", 1)[0].strip()
    if len(lines) >= 2:
        return lines[1]
    return ""


def _extract_links(text: str) -> Dict[str, str]:
    links: Dict[str, str] = {}
    for url in re.findall(r"https?://\S+", text):
        cleaned = url.rstrip(").,")
        lowered = cleaned.lower()
        if "linkedin.com" in lowered:
            links["linkedin"] = cleaned
        elif "github.com" in lowered:
            links["github"] = cleaned
        else:
            links.setdefault("website", cleaned)
    return links


def _extract_skills(sections: Dict[str, str], text: str) -> List[str]:
    skills_block = sections.get("SKILLS", "")
    candidates: List[str] = []
    for line in skills_block.splitlines():
        if ":" in line:
            _, values = line.split(":", 1)
            candidates.extend(part.strip() for part in values.split(","))
        else:
            candidates.extend(part.strip() for part in re.split(r"[•,]", line))
    lowered_text = text.lower()
    candidates.extend(keyword for keyword in KNOWN_KEYWORDS if keyword in lowered_text)
    return _dedupe(candidates)


def _infer_target_titles(text: str, keywords: List[str]) -> List[str]:
    lowered = text.lower()
    titles: List[str] = []
    if "full-stack" in lowered or "react" in lowered or "node.js" in lowered:
        titles.append("Full-Stack Developer")
    if "ai automation" in lowered or "llm" in lowered or "openai" in lowered:
        titles.append("AI Automation Engineer")
    if "python" in lowered:
        titles.append("Python Developer")
    if "software engineer" in lowered:
        titles.append("Entry-Level Software Engineer")
    if "react" in lowered or "typescript" in lowered:
        titles.append("React Developer")
    if "backend" in lowered or "fastapi" in lowered or "flask" in lowered:
        titles.append("Backend Developer")
    if not titles and keywords:
        titles.append("Software Developer")
    return _dedupe(titles)


def _estimate_experience_years(text: str) -> float | None:
    years = [int(value) for value in re.findall(r"\b(20\d{2})\b", text)]
    if not years:
        return None
    earliest = min(years)
    current_year = datetime.utcnow().year
    if earliest > current_year:
        return None
    return round(max(current_year - earliest, 0) + 0.5, 1)


def _extract_current_title(sections: Dict[str, str]) -> str:
    lines = [line.strip() for line in sections.get("EXPERIENCE", "").splitlines() if line.strip()]
    for line in lines:
        if line.lower().startswith("software engineer"):
            return line
    return lines[1] if len(lines) > 1 else ""


def parse_candidate_profile(text: str) -> CandidateProfile:
    sections = split_sections(text)
    header = sections.get("HEADER", "")
    objective = sections.get("OBJECTIVE", "")
    education = sections.get("EDUCATION", "")
    links = _extract_links(text)
    skills = _extract_skills(sections, text)
    target_titles = _infer_target_titles(text, skills)
    preferred_locations = _dedupe(
        [
            "Remote",
            "India",
            "Mohali",
            "Chandigarh",
            "New Delhi",
            "Bengaluru",
        ]
    )

    return CandidateProfile(
        full_name=_extract_name(header),
        email=_extract_email(text),
        phone=_extract_phone(text),
        location=_extract_location(header),
        summary=" ".join(objective.split()),
        current_title=_extract_current_title(sections),
        years_experience=_estimate_experience_years(sections.get("EXPERIENCE", text)),
        target_titles=target_titles,
        preferred_locations=preferred_locations,
        skills=skills,
        keywords=[keyword.lower() for keyword in skills],
        education=[line.strip() for line in education.splitlines() if line.strip()],
        links=links,
        custom_answers={},
    )


def apply_profile_overrides(profile: CandidateProfile, overrides: Dict[str, object]) -> CandidateProfile:
    if not overrides:
        return profile

    target_titles = overrides.get("target_titles")
    if isinstance(target_titles, list) and target_titles:
        profile.target_titles = _dedupe([str(item) for item in target_titles])

    preferred_locations = overrides.get("preferred_locations")
    if isinstance(preferred_locations, list) and preferred_locations:
        profile.preferred_locations = _dedupe([str(item) for item in preferred_locations])

    custom_answers = overrides.get("custom_answers")
    if isinstance(custom_answers, dict):
        profile.custom_answers.update({str(key): str(value) for key, value in custom_answers.items()})
        for link_name in ("linkedin", "github", "portfolio", "website"):
            if custom_answers.get(link_name):
                profile.links[link_name] = str(custom_answers[link_name])

    return profile
