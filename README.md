# AgriPride Kibaigwa MarketLink

AgriPride Kibaigwa MarketLink is a low-bandwidth, human-supervised agricultural market-transparency app for Kibaigwa International Grain Market in Dodoma Region, Tanzania.

The deadline build serves farmers through mobile web, a text-first `/lite` page, SMS-style callbacks, USSD-style callbacks, and a browser-based basic-phone simulator. It does not claim that a live Tanzania shortcode or live SMS sender has been provisioned.

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python -m app.main seed-demo
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

Default officer accounts from `.env.example`:

- Submitter: `submitter` / `submitter-pass`
- Reviewer: `reviewer` / `reviewer-pass`

## Core Routes

- Farmer web: `/`
- Low-bandwidth text page: `/lite`
- Public market dashboard: `/market`
- JSON price endpoint: `/api/v1/prices/maize`
- Plain-text endpoint: `/api/v1/prices/maize.txt`
- Channel simulator: `/channels/demo`
- USSD callback: `POST /channels/ussd/callback`
- SMS inbound callback: `POST /channels/sms/inbound`
- SMS delivery report: `POST /channels/sms/delivery-report`
- Officer portal: `/officer/login`
- Agent demo: `/agent-demo`

## Demo Seed

```powershell
.\.venv\Scripts\python -m app.main seed-demo
```

The seed creates approved demo ranges for maize, sunflower, and groundnuts. Groundnuts is intentionally stale to demonstrate the stale-price warning.

## SMS And USSD Smoke Tests

PowerShell:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/channels/sms/inbound -Body @{from="+255700123456"; text="MAHINDI"}
Invoke-RestMethod -Method Post http://127.0.0.1:8000/channels/ussd/callback -Body @{sessionId="demo1"; serviceCode="*700#"; phoneNumber="+255700123456"; text=""}
Invoke-RestMethod -Method Post http://127.0.0.1:8000/channels/ussd/callback -Body @{sessionId="demo1"; serviceCode="*700#"; phoneNumber="+255700123456"; text="1"}
```

curl:

```bash
curl -X POST http://127.0.0.1:8000/channels/sms/inbound -d "from=+255700123456" -d "text=MAHINDI"
curl -X POST http://127.0.0.1:8000/channels/ussd/callback -d "sessionId=demo1" -d "serviceCode=*700#" -d "phoneNumber=+255700123456" -d "text="
curl -X POST http://127.0.0.1:8000/channels/ussd/callback -d "sessionId=demo1" -d "serviceCode=*700#" -d "phoneNumber=+255700123456" -d "text=1"
```

USSD continuation responses start with `CON `. Final responses start with `END `.

## Render Deployment

The deadline app runs with SQLite fallback for local development and PostgreSQL when Render provides a managed Postgres `DATABASE_URL`.

Required environment variables:

- `APP_ENV=production`
- `DATABASE_URL` from Render PostgreSQL, or `sqlite:///./marketlink.db` for a disk-backed demo fallback
- `SECRET_KEY`
- `SUBMITTER_USERNAME`
- `SUBMITTER_PASSWORD`
- `SUBMITTER_OFFICER_ID`
- `REVIEWER_USERNAME`
- `REVIEWER_PASSWORD`
- `REVIEWER_OFFICER_ID`
- `FRESHNESS_THRESHOLD_HOURS=24`
- `SMS_PROVIDER=mock`
- `ENABLE_LIVE_SMS=false`

Optional Africa's Talking variables:

- `AT_USERNAME`
- `AT_API_KEY`
- `AT_SENDER_ID`
- `AT_ENVIRONMENT=sandbox`

## Provider Integration Position

SMS and USSD callbacks are provider-ready for form fields used by Africa's Talking-style integrations. The app masks phone numbers before persistence and keeps outbound SMS behind environment flags.

Live outbound SMS is disabled unless:

- `SMS_PROVIDER=africastalking`
- `AT_USERNAME` is present
- `AT_API_KEY` is present
- `ENABLE_LIVE_SMS=true`

The current adapter returns a guarded readiness result for Africa's Talking; plugging in the provider SDK/API send call should happen only after credentials, sender ID or shortcode setup, pricing, and Tanzania compliance checks are complete.

## Lecturer Demo Workflow

1. Run `.\.venv\Scripts\python -m app.main seed-demo`.
2. Open `/market` and show approved crop ranges.
3. Open `/channels/demo`.
4. Submit SMS text `MAHINDI` and show the concise reference-price disclaimer.
5. Submit blank USSD text and show the `CON` menu.
6. Submit USSD text `1` and show the `END` maize response.
7. Log in as submitter and submit a new range.
8. Log in as reviewer and approve it, showing self-approval is blocked if attempted by the submitter.
9. Repeat SMS or USSD to show the approved range.
10. Open `/agent-demo`, create a below-range or missing-scale synthetic case, and show Guardian flags plus Hunter briefing.
11. Record a human review decision.
12. Open `/officer/metrics` and show web, lite, SMS, USSD, and agent metrics.

## Tests

```powershell
.\.venv\Scripts\python -m pytest -q
```
