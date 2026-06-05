# AGENTS.md — AgriPride Kibaigwa MarketLink Award Mode + Low-Bandwidth Channels

## Deadline objective
Build and deploy an award-ready capstone web application under severe time constraints. The solution must visibly address real rural African access constraints: feature phones, intermittent internet, low data budgets, SMS, and USSD.

Protect the critical path:
1. deploy a working web app;
2. include low-bandwidth public access;
3. expose provider-ready SMS and USSD callback endpoints;
4. include a basic-phone channel simulator;
5. demonstrate Scout → Guardian → Hunter → human review;
6. run tests before deployment.

Do not block deployment on real telecom shortcode provisioning or external provider approval.

## Product vision
AgriPride Kibaigwa MarketLink is a low-bandwidth, human-supervised agricultural market-transparency platform for Kibaigwa International Grain Market in Kongwa District, Dodoma Region, Tanzania.

Farmers should be able to retrieve approved reference-price information through:
- lightweight mobile web;
- text-only web;
- SMS-style query;
- USSD-style menu.

## Honest telecom position
For the capstone deadline:
- implement provider-ready SMS and USSD webhook contracts;
- implement a working in-app SMS/USSD simulator;
- make external SMS sending optional behind environment variables;
- do not claim that a live Tanzania shortcode or live SMS sender is provisioned unless credentials and provider setup actually exist.

## Tier 1 — must ship

### Public farmer access
1. `/` mobile-first farmer page.
2. `/lite` text-first, very low-bandwidth farmer page with minimal markup and no JavaScript dependency.
3. `/market` public market dashboard.
4. `/api/v1/prices/{crop}` JSON endpoint.
5. `/api/v1/prices/{crop}.txt` plain-text endpoint suitable for constrained clients.

### Officer portal
1. Login.
2. Submit pending price range.
3. Reviewer approve or reject.
4. Self-approval blocked server-side.
5. Audit trail.
6. Metrics dashboard.

### SMS and USSD channels
1. `/channels/demo` browser-based basic-phone simulator.
2. `/channels/ussd/callback` POST callback endpoint with Africa's Talking-compatible request fields:
   - `sessionId`
   - `serviceCode`
   - `phoneNumber`
   - `text`
3. `/channels/sms/inbound` POST callback endpoint:
   - `from`
   - `text`
4. `/channels/sms/delivery-report` POST callback endpoint for provider delivery states.
5. Query logs must mask phone numbers before persistence.
6. USSD responses must use `CON ` for menu continuation and `END ` for final responses.
7. SMS responses must remain concise and include reference-price disclaimer.

### Agentic terrain demo
Implement `/agent-demo` with Scout → Guardian → Hunter → human review using synthetic transaction data only.

### PWA and offline-friendly web
Add:
- manifest;
- offline page;
- service worker caching only safe public assets;
- no caching of officer pages, personal data, or sensitive API responses.

### Deployment
- SQLite local fallback.
- PostgreSQL support via `DATABASE_URL`.
- Render config.
- Tests.

## Tier 2 — implement after Tier 1 passes
1. Multi-crop support:
   - maize
   - sunflower
   - groundnuts
2. Kiswahili / English toggle.
3. Channel metrics by web, lite, SMS, and USSD.
4. Demo data seed command.
5. SMS provider adapter with optional Africa's Talking SDK integration when credentials are present.
6. Configurable provider mode:
   - `mock`
   - `sandbox`
   - `production`
7. CSV audit export.
8. Historical price table.

## Tier 3 — only after deployed app works
1. SVG price trends.
2. Accessibility polish.
3. QR code card to public app.
4. Screenshot section in README.
5. Additional assisted-support workflow.

## Supported crops
Canonical keys:
- `maize`
- `sunflower`
- `groundnuts`

Display labels:
- maize → Mahindi / Maize
- sunflower → Alizeti / Sunflower
- groundnuts → Karanga / Groundnuts

## Public farmer flow
1. Farmer opens `/` or `/lite`.
2. Selects crop.
3. Sees latest approved reference range or stale/unavailable warning.
4. Sees update timestamp and human-approved source.
5. Sees note: reference range, not guaranteed buyer offer.
6. Query is logged by channel without unnecessary personal data.

## Low-bandwidth design rules
- Farmer-facing pages must work without JavaScript.
- `/lite` should prioritize HTML text and forms only.
- Keep farmer page payload small; avoid heavy frameworks and large images.
- Use server-rendered templates.
- Do not require account creation for farmer price lookup.
- Provide concise text messages.
- Avoid unnecessary web fonts, large libraries, animations, or trackers.
- Treat SMS and USSD as first-class channels, not marketing add-ons.

## USSD flow

### Request contract
Provider callback:
- POST `/channels/ussd/callback`
- form fields: `sessionId`, `serviceCode`, `phoneNumber`, `text`

### Menu behavior
Initial:
`CON Karibu MarketLink
1. Bei ya mahindi
2. Bei ya alizeti
3. Bei ya karanga
4. Msaada`

Selection 1:
Return `END ` plus fresh, stale, or unavailable Kiswahili message for maize.

Selection 2:
Return `END ` plus fresh, stale, or unavailable Kiswahili message for sunflower.

Selection 3:
Return `END ` plus fresh, stale, or unavailable Kiswahili message for groundnuts.

Selection 4:
`END Kwa msaada piga *700# au wasiliana na afisa wa soko.`

Invalid:
`END Chaguo si sahihi. Tafadhali jaribu tena.`

### USSD privacy
- Do not store raw phone number.
- Store masked form only.
- Log session channel and response state.
- Keep menus concise.

## SMS flow

### Request contract
Provider callback:
- POST `/channels/sms/inbound`
- form fields: `from`, `text`

### Accepted query keywords
- `MAHINDI`
- `MAIZE`
- `ALIZETI`
- `SUNFLOWER`
- `KARANGA`
- `GROUNDNUTS`
- `MSAADA`
- `HELP`

### Behavior
- Parse crop keyword deterministically.
- Return concise Kiswahili or bilingual message.
- Log masked sender and response state.
- If keyword unknown, return usage help.
- Do not send external SMS unless provider mode and credentials explicitly allow it.

### Optional outbound adapter
Implement a small provider interface:
- `MockSmsProvider`
- `AfricasTalkingSmsProvider`

Default to `MockSmsProvider`.
Use external API only when:
- `SMS_PROVIDER=africastalking`
- `AT_USERNAME` exists
- `AT_API_KEY` exists
- `ENABLE_LIVE_SMS=true`

Never fail the core app if provider credentials are absent.

## Officer flow
Routes:
- `/officer/login`
- `/officer/logout`
- `/officer/dashboard`
- `/officer/prices`
- `/officer/prices/new`
- `/officer/prices/{id}/review`
- `/officer/audit`
- `/officer/metrics`

## Agent Savannah demo
Route:
- `/agent-demo`

Use synthetic fields only:
- crop;
- offered price;
- quantity kg;
- scale ID state;
- payment state;
- buyer or broker record state.

Scout:
- retrieves latest approved range.

Guardian:
- deterministic flags:
  - `offer_below_reference_range`
  - `missing_scale_id`
  - `missing_actor_record`
  - `payment_delayed`
  - `payment_disputed`

Hunter:
- neutral briefing;
- human review required.

No automatic punishment.
No blacklisting.
No fraud accusation.

## Framework mapping

### Scout — RANK
Role: retrieve human-approved market data.
Authority: retrieve and format only.
Notification: stale, missing, incomplete.
Kill switch: never show stale or unapproved record as current.

### Scout — GUARD
No approved source and timestamp means no current-price message.

### Scout — CYCLE
Capture query counts by crop, state, and channel: web, lite, SMS, USSD.

### Guardian — RANK
Role: flag synthetic case issues.
Authority: flag only.
Notification: deterministic flags.
Kill switch: pause case completion and require human review.

### Guardian — TRAIL
Transient: active synthetic case.
Relational: approved price and synthetic actor state.
Archival: anonymized flag counts.
Inheritance: minimum handoff payload.
Land Rights: no unnecessary personal identifiers.

### Guardian — GUARD
Flag is a request for review, not proof of misconduct.

### Guardian — CYCLE
Capture flags and review outcomes.

### Hunter — RANK
Role: neutral briefing and routing.
Authority: summarize only.
Notification: flagged case.
Kill switch: no autonomous resolution.

### Hunter — HUNT
Handoff trigger: Guardian flag.
Useful payload: case ID, crop, reference range, offered price, quantity, scale state, payment state, actor record state, flags.
Next-agent check: reject unnecessary personal data.
Transfer: human review decision.

### Hunter — GUARD
Separate facts, missing evidence, and requested action.

### Hunter — CYCLE
Capture review outcomes and resolution time.

### PRIDE
- second-officer approval;
- stale-price pause;
- flagged-case human review;
- audit ownership;
- visible appeal/support route.

## Privacy constraints
- Do not collect farmer name, village, GPS location, transaction history, or payment history in public farmer channels.
- Mask phone numbers before persistence.
- Do not cache sensitive routes.
- No raw identifiers in model prompts or logs.
- No personalized pricing.
- No farmer scoring.
- No automated sell/wait advice.

## Environment variables
Required:
- `APP_ENV`
- `DATABASE_URL`
- `SECRET_KEY`
- `SUBMITTER_USERNAME`
- `SUBMITTER_PASSWORD`
- `SUBMITTER_OFFICER_ID`
- `REVIEWER_USERNAME`
- `REVIEWER_PASSWORD`
- `REVIEWER_OFFICER_ID`
- `FRESHNESS_THRESHOLD_HOURS`

Optional SMS:
- `SMS_PROVIDER=mock`
- `ENABLE_LIVE_SMS=false`
- `AT_USERNAME`
- `AT_API_KEY`
- `AT_SENDER_ID`
- `AT_ENVIRONMENT=sandbox`

## Required routes
Public:
- `GET /`
- `GET /lite`
- `GET /market`
- `GET /health`
- `GET /offline.html`
- `GET /api/v1/prices/{crop}`
- `GET /api/v1/prices/{crop}.txt`

Channels:
- `GET /channels/demo`
- `POST /channels/ussd/callback`
- `POST /channels/sms/inbound`
- `POST /channels/sms/delivery-report`

Officer:
- `GET /officer/login`
- `POST /officer/login`
- `POST /officer/logout`
- `GET /officer/dashboard`
- `GET /officer/prices`
- `GET /officer/prices/new`
- `POST /officer/prices/new`
- `GET /officer/prices/{price_id}/review`
- `POST /officer/prices/{price_id}/review`
- `GET /officer/audit`
- `GET /officer/metrics`

Agent demo:
- `GET /agent-demo`
- `POST /agent-demo`
- `POST /agent-demo/{case_id}/review`

## Persistence models
- `PriceRecord`
- `AuditEvent`
- `FarmerQuery`
- `ChannelDeliveryEvent`
- `AgentDemoCase`
- `GuardianFlag`
- `HunterBriefing`
- `HumanReviewDecision`

## Required tests
At minimum:
1. health endpoint;
2. farmer page;
3. lite page;
4. market page;
5. plain text price endpoint;
6. invalid range rejected;
7. submission pending;
8. self-approval blocked;
9. reviewer approval;
10. fresh, stale, unavailable states;
11. audit events;
12. multi-crop support;
13. USSD menu initial response starts with `CON `;
14. USSD crop selection returns `END `;
15. USSD unavailable state;
16. SMS crop keyword parsing;
17. SMS unknown keyword help;
18. masked phone stored in channel log;
19. Guardian below-range flag;
20. Guardian missing-scale flag;
21. Hunter briefing;
22. clean case no Hunter briefing;
23. human decision logged;
24. no automatic punishment;
25. officer auth;
26. service worker and manifest available.

## Deadline discipline
- Ship Tier 1 first.
- Run tests.
- Deploy.
- Add Tier 2 only when Tier 1 works.
- Do not wait for real Tanzania shortcode provisioning.
- Do not add React, live payment integration, farmer scoring, or LLM calls.
- Do not push, merge, or deploy without explicit approval.
