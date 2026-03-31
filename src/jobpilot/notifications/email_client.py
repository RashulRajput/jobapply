from __future__ import annotations

import email
import imaplib
import os
import re
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List

from jobpilot.models import CandidateProfile, JobPosting


INTERVIEW_FALLBACK_KEYWORDS = [
    "interview",
    "shortlisted",
    "screening",
    "assessment",
    "schedule",
    "next round",
    "technical round",
]


def _get_password(email_config: Dict[str, object]) -> str:
    env_name = str(email_config.get("app_password_env", "JOBPILOT_GMAIL_APP_PASSWORD"))
    return os.environ.get(env_name, "")


def build_hr_email(profile: CandidateProfile, job: JobPosting) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = f"Application Interest: {job.title} at {job.company}"
    message.set_content(
        "\n".join(
            [
                f"Hello {job.company} hiring team,",
                "",
                f"I recently applied for the {job.title} role and wanted to share a short note of interest.",
                f"My background lines up strongly with {', '.join(profile.target_titles[:3])}, and I have hands-on experience with {', '.join(profile.skills[:8])}.",
                f"I am currently based in {profile.location} and am open to remote or India-based opportunities.",
                "",
                f"Resume summary: {profile.summary}",
                "",
                f"Best regards,",
                profile.full_name,
                profile.email,
                profile.phone,
            ]
        )
    )
    return message


def send_email_message(
    email_config: Dict[str, object],
    message: EmailMessage,
    to_addresses: List[str],
    resume_path: str | None = None,
) -> None:
    password = _get_password(email_config)
    if not password:
        raise RuntimeError("Missing Gmail app password environment variable.")

    username = str(email_config["username"])
    message["From"] = username
    message["To"] = ", ".join(to_addresses)

    if resume_path:
        attachment_path = Path(resume_path)
        if attachment_path.exists():
            message.add_attachment(
                attachment_path.read_bytes(),
                maintype="application",
                subtype="pdf",
                filename=attachment_path.name,
            )

    smtp_host = str(email_config.get("smtp_host", "smtp.gmail.com"))
    smtp_port = int(email_config.get("smtp_port", 587))
    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(message)


def _extract_text_from_message(message_obj: email.message.Message) -> str:
    if message_obj.is_multipart():
        parts: List[str] = []
        for part in message_obj.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                parts.append(payload.decode(charset, errors="ignore"))
        return "\n".join(parts)
    payload = message_obj.get_payload(decode=True) or b""
    charset = message_obj.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="ignore")


def scan_inbox_for_interviews(email_config: Dict[str, object]) -> List[Dict[str, str]]:
    password = _get_password(email_config)
    if not password:
        return []

    username = str(email_config["username"])
    host = str(email_config.get("imap_host", "imap.gmail.com"))
    port = int(email_config.get("imap_port", 993))
    days_to_scan = int(email_config.get("days_to_scan", 14))
    keywords = [
        str(item).lower()
        for item in email_config.get("interview_keywords", INTERVIEW_FALLBACK_KEYWORDS)
    ]
    cutoff = (datetime.utcnow() - timedelta(days=days_to_scan)).strftime("%d-%b-%Y")

    matches: List[Dict[str, str]] = []
    with imaplib.IMAP4_SSL(host, port) as mailbox:
        mailbox.login(username, password)
        mailbox.select("INBOX")
        status, data = mailbox.search(None, f'(SINCE "{cutoff}")')
        if status != "OK":
            return []
        message_ids = list(reversed(data[0].split()))
        for message_id in message_ids[:100]:
            status, fetched = mailbox.fetch(message_id, "(RFC822)")
            if status != "OK":
                continue
            raw_message = fetched[0][1]
            message_obj = email.message_from_bytes(raw_message)
            subject = str(email.header.make_header(email.header.decode_header(message_obj.get("Subject", ""))))
            sender = str(email.header.make_header(email.header.decode_header(message_obj.get("From", ""))))
            body = _extract_text_from_message(message_obj)
            searchable = f"{subject}\n{sender}\n{body}".lower()
            if any(keyword in searchable for keyword in keywords):
                clean_body = re.sub(r"\s+", " ", body).strip()
                matches.append(
                    {
                        "subject": subject,
                        "from": sender,
                        "date": message_obj.get("Date", ""),
                        "snippet": clean_body[:240],
                    }
                )
    return matches
