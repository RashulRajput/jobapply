# JobPilot

JobPilot is a local Python automation that uses your resume to:

- parse your profile from PDF or DOCX
- search developer jobs from public job sources
- score those jobs against your resume with ATS-style keyword matching
- open supported application flows in Playwright and submit when the form is complete
- pause and hand control back to you for CAPTCHA or unknown required questions
- send HR outreach emails when a recruiter email is available
- scan Gmail for interview-related replies

This first build is tailored to your current resume at `C:\Users\DELL\Downloads\fullstackresume.pdf` and defaults to:

- entry-level software engineer / full-stack developer / Python / React / Node.js / AI automation roles
- remote and India-based opportunities
- aggressive auto-apply when the form is fillable end-to-end

## What It Supports

- Resume parsing with `pypdf`, with a `pdftotext` fallback.
- Public job discovery from `Arbeitnow` and `Remote OK`.
- Browser automation with `Playwright`.
- Gmail sending and inbox scanning with SMTP + IMAP.
- Deterministic generated site passwords using `JOBPILOT_PASSWORD_SEED` for account-creation forms.

## Current Limits

- Job sites that require unusual multi-step workflows or hidden anti-bot systems may need manual help.
- CAPTCHAs are not bypassed. The bot pauses and asks you to solve them.
- HR outreach only happens when the job page exposes a usable email address.
- Gmail sending and inbox monitoring require a Gmail app password in `JOBPILOT_GMAIL_APP_PASSWORD`.

## Quick Start

1. Install dependencies:

```powershell
python -m pip install --user -r requirements.txt
python -m playwright install chromium
```

2. Optional but recommended PowerShell environment variables:

```powershell
$env:JOBPILOT_PASSWORD_SEED = "choose-a-long-random-secret"
$env:JOBPILOT_GMAIL_APP_PASSWORD = "your-gmail-app-password"
```

3. Review the config in [config/jobpilot.json](C:/Users/DELL/OneDrive/Documents/New%20project/config/jobpilot.json).

4. Inspect the inferred profile:

```powershell
python run_jobpilot.py --config config/jobpilot.json profile
```

5. Search jobs without applying:

```powershell
python run_jobpilot.py --config config/jobpilot.json search --limit 15
```

6. Run the aggressive pipeline:

```powershell
python run_jobpilot.py --config config/jobpilot.json run --limit 10
```

7. Check interview-style inbox updates:

```powershell
python run_jobpilot.py --config config/jobpilot.json watch-inbox
```

## Files

- [run_jobpilot.py](C:/Users/DELL/OneDrive/Documents/New%20project/run_jobpilot.py): top-level entry point
- [config/jobpilot.json](C:/Users/DELL/OneDrive/Documents/New%20project/config/jobpilot.json): search, application, and email settings
- [src/jobpilot/resume.py](C:/Users/DELL/OneDrive/Documents/New%20project/src/jobpilot/resume.py): resume parsing and profile inference
- [src/jobpilot/providers/search.py](C:/Users/DELL/OneDrive/Documents/New%20project/src/jobpilot/providers/search.py): job providers
- [src/jobpilot/application/browser.py](C:/Users/DELL/OneDrive/Documents/New%20project/src/jobpilot/application/browser.py): Playwright auto-apply flow
- [src/jobpilot/notifications/email_client.py](C:/Users/DELL/OneDrive/Documents/New%20project/src/jobpilot/notifications/email_client.py): Gmail sending and inbox checks

## Safe Operating Mode

The bot is configured for aggressive search and submission, but it still protects against the highest-risk failure cases:

- it skips jobs already applied to
- it pauses for CAPTCHA
- it pauses when required fields remain unknown
- it avoids blind resubmission loops by saving state in `data/state.json`
