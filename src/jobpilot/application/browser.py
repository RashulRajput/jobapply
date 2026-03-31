from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import Page, sync_playwright

from jobpilot.models import ApplicationResult, CandidateProfile, JobPosting


SUBMIT_TEXTS = [
    "submit application",
    "apply now",
    "submit",
    "send application",
    "complete application",
]

SUCCESS_PATTERNS = [
    "thank you for applying",
    "application submitted",
    "we have received your application",
    "thanks for applying",
    "your application has been submitted",
]

CAPTCHA_PATTERNS = [
    "captcha",
    "i'm not a robot",
    "verify you are human",
]


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def _make_password(domain: str) -> str:
    seed = os.environ.get("JOBPILOT_PASSWORD_SEED", "")
    if not seed:
        return ""
    digest = hashlib.sha256(f"{seed}:{domain}".encode("utf-8")).hexdigest()
    return f"Jp!{digest[:10]}Aa9"


def _build_cover_letter(profile: CandidateProfile, job: JobPosting) -> str:
    strengths = ", ".join(profile.skills[:8])
    return (
        f"I am excited to apply for the {job.title} role at {job.company}. "
        f"My background includes {strengths}, along with hands-on work in AI automation, "
        f"full-stack development, and data pipelines. I would be glad to contribute quickly "
        f"to {job.company} in an entry-level engineering capacity."
    )


def _candidate_values(profile: CandidateProfile, job: JobPosting, answer_map: Dict[str, str], domain: str) -> Dict[str, str]:
    full_name_parts = profile.full_name.split()
    first_name = full_name_parts[0] if full_name_parts else profile.full_name
    last_name = " ".join(full_name_parts[1:]) if len(full_name_parts) > 1 else ""
    generated_password = _make_password(domain)

    years = ""
    if profile.years_experience is not None:
        years = str(profile.years_experience)

    return {
        "first_name": first_name,
        "last_name": last_name,
        "full_name": profile.full_name,
        "email": profile.email,
        "phone": profile.phone,
        "linkedin": profile.links.get("linkedin", ""),
        "github": profile.links.get("github", ""),
        "portfolio": profile.links.get("portfolio", "") or profile.links.get("website", ""),
        "location": profile.location,
        "current_title": profile.current_title,
        "experience_years": years or "1-3",
        "university": profile.custom_answers.get("university", ""),
        "graduation": profile.custom_answers.get("graduation month year", ""),
        "degree": profile.custom_answers.get("highest degree", ""),
        "password": generated_password,
        "cover_letter": _build_cover_letter(profile, job),
        "work authorization": answer_map.get("work authorization", ""),
        "visa sponsorship": answer_map.get("visa sponsorship", ""),
        "relocate": answer_map.get("relocate", ""),
        "notice period": answer_map.get("notice period", ""),
        "current ctc": answer_map.get("current ctc", ""),
        "expected ctc": answer_map.get("expected ctc", ""),
        "gender": answer_map.get("gender", ""),
        "disability": answer_map.get("disability", ""),
        "veteran": answer_map.get("veteran", ""),
        "ethnicity": answer_map.get("ethnicity", ""),
    }


def _match_field_value(descriptor: str, values: Dict[str, str]) -> str:
    mapping = [
        (["first name", "given name"], "first_name"),
        (["last name", "surname", "family name"], "last_name"),
        (["full name", "your name", "applicant name"], "full_name"),
        (["email"], "email"),
        (["phone", "mobile", "contact number"], "phone"),
        (["linkedin"], "linkedin"),
        (["github"], "github"),
        (["portfolio", "website", "personal site"], "portfolio"),
        (["location", "city", "address"], "location"),
        (["current title", "job title", "designation"], "current_title"),
        (["years of experience", "experience"], "experience_years"),
        (["university", "college", "school"], "university"),
        (["graduation", "graduated", "completion"], "graduation"),
        (["degree", "education"], "degree"),
        (["cover letter", "why are you interested", "why do you want"], "cover_letter"),
        (["authorization", "authorized to work"], "work authorization"),
        (["visa sponsorship", "sponsorship"], "visa sponsorship"),
        (["relocate"], "relocate"),
        (["notice period"], "notice period"),
        (["current ctc", "current salary"], "current ctc"),
        (["expected ctc", "expected salary", "salary expectation"], "expected ctc"),
        (["gender"], "gender"),
        (["disability"], "disability"),
        (["veteran"], "veteran"),
        (["ethnicity", "race"], "ethnicity"),
        (["confirm password", "password confirmation"], "password"),
        (["password"], "password"),
    ]
    for aliases, value_key in mapping:
        if any(alias in descriptor for alias in aliases):
            return values.get(value_key, "")
    return ""


def _collect_visible_fields(page: Page) -> List[Dict[str, object]]:
    return page.evaluate(
        """
        () => {
          const nodes = Array.from(document.querySelectorAll('input, textarea, select'));
          const isVisible = (node) => {
            const style = window.getComputedStyle(node);
            const rect = node.getBoundingClientRect();
            return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
          };
          return nodes.map((node, index) => {
            const labels = [];
            if (node.id) {
              const label = document.querySelector(`label[for="${node.id}"]`);
              if (label) labels.push(label.innerText || label.textContent || '');
            }
            const parentLabel = node.closest('label');
            if (parentLabel) labels.push(parentLabel.innerText || parentLabel.textContent || '');
            return {
              index,
              tag: node.tagName.toLowerCase(),
              type: (node.getAttribute('type') || '').toLowerCase(),
              name: node.getAttribute('name') || '',
              id: node.id || '',
              placeholder: node.getAttribute('placeholder') || '',
              ariaLabel: node.getAttribute('aria-label') || '',
              required: Boolean(node.required || node.getAttribute('aria-required') === 'true' || node.getAttribute('required') !== null),
              visible: isVisible(node),
              labels,
              value: node.value || ''
            };
          }).filter((item) => item.visible);
        }
        """
    )


def _descriptor(field: Dict[str, object]) -> str:
    parts = [
        *[str(item) for item in field.get("labels", [])],
        str(field.get("name", "")),
        str(field.get("id", "")),
        str(field.get("placeholder", "")),
        str(field.get("ariaLabel", "")),
    ]
    return _normalize(" ".join(parts))


def _choose_select_option(options: List[Dict[str, str]], value: str) -> str:
    normalized_value = _normalize(value)
    if not normalized_value:
        return ""
    for option in options:
        label = _normalize(option.get("label", ""))
        if normalized_value in label or label in normalized_value:
            return option.get("value", "")
    for option in options:
        label = _normalize(option.get("label", ""))
        if normalized_value == "prefer not to say" and "prefer" in label:
            return option.get("value", "")
    return ""


def _fill_fields(page: Page, profile: CandidateProfile, job: JobPosting, config: Dict[str, object]) -> List[str]:
    answer_map = {
        str(key).lower(): str(value)
        for key, value in config.get("answer_map", {}).items()
    }
    domain = urlparse(job.apply_url or job.url).netloc
    values = _candidate_values(profile, job, answer_map, domain)
    resume_path = Path(str(config.get("resume_upload_path", "")))
    unknown_required_fields: List[str] = []

    fields = _collect_visible_fields(page)
    all_nodes = page.locator("input, textarea, select")

    for field in fields:
        descriptor = _descriptor(field)
        locator = all_nodes.nth(int(field["index"]))
        field_type = str(field.get("type", ""))
        tag = str(field.get("tag", ""))

        if field_type in {"hidden", "submit", "button"}:
            continue

        if field_type == "file":
            if resume_path.exists():
                locator.set_input_files(str(resume_path))
            continue

        value = _match_field_value(descriptor, values)

        if tag == "select" and value:
            options = locator.evaluate(
                """
                el => Array.from(el.options).map(option => ({
                  value: option.value || '',
                  label: option.textContent || ''
                }))
                """
            )
            selected = _choose_select_option(options, value)
            if selected:
                locator.select_option(value=selected)
            continue

        if field_type in {"checkbox", "radio"}:
            if value and value.lower().startswith("yes"):
                try:
                    locator.check(force=True)
                except Exception:
                    pass
            continue

        if value:
            try:
                locator.fill(value)
            except Exception:
                continue
        elif field.get("required"):
            unknown_required_fields.append(descriptor or f"field-{field['index']}")

    return unknown_required_fields


def _has_captcha(page: Page) -> bool:
    content = _normalize(page.content())
    if any(pattern in content for pattern in CAPTCHA_PATTERNS):
        return True
    try:
        return page.locator("iframe[src*='captcha'], iframe[title*='captcha']").count() > 0
    except Exception:
        return False


def _pause_for_user(message: str) -> None:
    print(message)
    input("Press Enter after you finish the action in the browser...")


def _submit_application(page: Page) -> bool:
    for text in SUBMIT_TEXTS:
        button_locator = page.get_by_role("button", name=re.compile(text, re.I))
        if button_locator.count() > 0:
            button_locator.first.click()
            return True
        submit_locator = page.locator(f"input[type='submit'][value*='{text}']")
        if submit_locator.count() > 0:
            submit_locator.first.click()
            return True
    return False


def _was_successful(page: Page) -> bool:
    content = _normalize(page.content())
    return any(pattern in content for pattern in SUCCESS_PATTERNS)


def _extract_contact_emails(page: Page) -> List[str]:
    text = page.content()
    emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    filtered: List[str] = []
    for email_address in emails:
        lowered = email_address.lower()
        if lowered.startswith("noreply") or "example.com" in lowered:
            continue
        if lowered not in filtered:
            filtered.append(lowered)
    return filtered[:5]


def _is_supported_domain(job: JobPosting, supported_domains: List[str]) -> bool:
    domain = urlparse(job.apply_url or job.url).netloc.lower()
    return any(value in domain for value in supported_domains)


def apply_to_jobs(
    jobs: List[JobPosting],
    profile: CandidateProfile,
    application_config: Dict[str, object],
) -> List[ApplicationResult]:
    browser_dir = Path(str(application_config["persisted_browser_dir"]))
    browser_dir.mkdir(parents=True, exist_ok=True)
    headless = bool(application_config.get("headless", False))
    pause_on_captcha = bool(application_config.get("pause_on_captcha", True))
    pause_on_unknown = bool(application_config.get("pause_on_unknown_required_fields", True))
    supported_domains = [str(item).lower() for item in application_config.get("supported_domains", [])]
    supported_only = bool(application_config.get("auto_submit_supported_sites_only", False))

    results: List[ApplicationResult] = []

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(browser_dir),
            headless=headless,
            accept_downloads=False,
        )
        page = context.new_page()
        for job in jobs:
            target_url = job.apply_url or job.url
            if not target_url:
                results.append(
                    ApplicationResult(
                        job_id=job.id,
                        company=job.company,
                        title=job.title,
                        url=job.url,
                        status="skipped",
                        detail="Missing application URL.",
                    )
                )
                continue

            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except PlaywrightTimeoutError:
                    pass

                contact_emails = _extract_contact_emails(page)
                unknown_required = _fill_fields(page, profile, job, application_config)

                if pause_on_captcha and _has_captcha(page):
                    _pause_for_user(
                        f"CAPTCHA detected for {job.company} - {job.title}. Solve it in the browser."
                    )

                if unknown_required and pause_on_unknown:
                    pretty_fields = ", ".join(unknown_required[:6])
                    _pause_for_user(
                        f"Required fields still need review for {job.company} - {job.title}: {pretty_fields}"
                    )

                if supported_only and not _is_supported_domain(job, supported_domains):
                    results.append(
                        ApplicationResult(
                            job_id=job.id,
                            company=job.company,
                            title=job.title,
                            url=target_url,
                            status="needs_user_action",
                            detail="Opened the job page, but auto-submit is limited to supported domains.",
                            contact_emails=contact_emails,
                        )
                    )
                    continue

                submitted = _submit_application(page)
                if submitted:
                    try:
                        page.wait_for_load_state("networkidle", timeout=12000)
                    except PlaywrightTimeoutError:
                        pass
                    status = "submitted" if _was_successful(page) else "submitted_unconfirmed"
                    detail = "Application was submitted automatically." if status == "submitted" else "Submit was clicked, but the confirmation message was not explicit."
                else:
                    status = "needs_user_action"
                    detail = "No obvious submit button was found."

                results.append(
                    ApplicationResult(
                        job_id=job.id,
                        company=job.company,
                        title=job.title,
                        url=target_url,
                        status=status,
                        detail=detail,
                        contact_emails=contact_emails,
                    )
                )
            except Exception as exc:
                results.append(
                    ApplicationResult(
                        job_id=job.id,
                        company=job.company,
                        title=job.title,
                        url=target_url,
                        status="error",
                        detail=str(exc),
                    )
                )
        context.close()

    return results
