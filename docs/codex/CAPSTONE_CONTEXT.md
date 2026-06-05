# CAPSTONE_CONTEXT.md — Low-Bandwidth African Context

## Core argument
MarketLink is not merely a web dashboard. Its core purpose is to serve farmers who may have feature phones, intermittent connectivity, limited data budgets, and limited access to up-to-date market information.

## Required channels
1. Lightweight mobile web.
2. Text-first `/lite` page.
3. SMS callback endpoint and simulator.
4. USSD callback endpoint and simulator.
5. Provider-ready architecture for Tanzania deployment.

## Honest deadline position
A real USSD shortcode often requires provisioning, commercial setup, and telco coordination. The deadline build must therefore:
- deploy callback endpoints;
- simulate complete SMS and USSD journeys;
- log channel outcomes;
- document the provider integration path;
- avoid falsely claiming a live shortcode.

## Why this strengthens the award submission
- demonstrates real African-context design;
- serves feature phones, not only smartphones;
- shows low-bandwidth engineering decisions;
- keeps human-approved data at the center;
- provides a believable path from demo to field pilot.

## Live demo script
1. Lecturer opens `/market` and sees approved crop prices.
2. Lecturer opens `/channels/demo`.
3. Simulate SMS query `MAHINDI`.
4. See short Kiswahili response.
5. Simulate USSD initial request.
6. See `CON` crop menu.
7. Select `1`.
8. See `END` maize price response.
9. Open officer portal and approve a new crop price.
10. Repeat USSD or SMS simulation.
11. Open `/agent-demo` and run synthetic Guardian/Hunter workflow.
12. Show metrics by web, lite, SMS, and USSD channels.

## External integration path
Preferred first provider evaluation: Africa's Talking or another Tanzania-compatible aggregator.
Do not hard-code provider dependence.
Use adapter pattern and environment flags.
