# CODEX_DEPLOY_PROMPT.md — Deployment with Low-Bandwidth Channels

Read `AGENTS.md`.
Inspect completed code.

## Verify
1. `pytest -q`.
2. No secrets tracked.
3. `/health`.
4. `/`.
5. `/lite`.
6. `/market`.
7. `/channels/demo`.
8. POST `/channels/ussd/callback`.
9. POST `/channels/sms/inbound`.
10. `/agent-demo`.
11. Officer approval flow.
12. PostgreSQL compatibility.
13. `render.yaml`.
14. service worker caching safe public assets only.
15. raw phone numbers are masked before persistence.

## Provide
- test results;
- Git commands;
- Render deployment steps;
- Supabase setup steps;
- provider-ready SMS/USSD path;
- PowerShell smoke-test commands;
- lecturer demo script;
- screenshots checklist;
- honest limitations:
  - no live Tanzania shortcode unless provisioned;
  - no real telecom SMS unless credentials enabled;
  - callback endpoints and simulator are live;
  - public web and lite channel are live.
