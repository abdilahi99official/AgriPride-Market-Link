# CODEX_BUILD_PROMPT.md — Award Mode + Low-Bandwidth Channels

Read:
- `AGENTS.md`
- `docs/codex/CAPSTONE_CONTEXT.md`

Implement the complete deadline build.

## Order
1. Inspect repository.
2. Implement Tier 1.
3. Run tests and fix.
4. Implement Tier 2 if time remains.
5. Run tests and fix.
6. Prepare Render deployment.
7. Report status.
8. Do not push, merge, or deploy externally without approval.

## Critical emphasis
SMS, USSD, and low-bandwidth access are core requirements.
Do not implement them as static text only.
Implement:
- working callback endpoints;
- masking and logs;
- browser simulator;
- concise menus and messages;
- provider adapter interface;
- optional Africa's Talking adapter guarded by environment variables;
- no dependency on external credentials for local tests or demo.

## Payload budget
- `/lite` must be text-first and usable without JavaScript.
- Avoid large images and heavy libraries.
- Use server-rendered HTML.
- Keep public CSS small.
- Do not cache private routes.

## Deployment
Add:
- `render.yaml`
- PostgreSQL support
- SQLite fallback
- `.env.example`
- README local setup
- README Render deployment
- README provider integration path
- smoke-test commands for SMS and USSD callbacks using curl or PowerShell

## Return
1. files changed;
2. dependencies;
3. full pytest output;
4. local run command;
5. seed-demo command;
6. SMS and USSD test commands;
7. Render environment variables;
8. lecturer demo workflow;
9. provider integration limitations;
10. git status.
