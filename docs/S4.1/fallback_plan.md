# Presentation-Day Fallback Plan

**Project:** BARQ G3 — AI ServiceNow Support Assistant

This plan covers what **we, the presenters, physically do in the room** if something breaks mid-demo — not backend recovery procedures for engineers after the fact. All three scenarios below are rehearsed in advance, not improvised on the day.

---

## Pre-Presentation Readiness (prepared once, used for any scenario)

Two things are set up and tested **before** we walk into the room, as a team:

1. **A pre-staged "mocked" incident already visible in ServiceNow** — a ticket that has already gone through the full pipeline and shows a completed, approved result (all five AI fields populated, approval action already available to demonstrate). If live processing fails or takes too long, we open this ticket instead and walk through the *result* while narrating the story — this is not a video, it's us live-navigating a real ServiceNow record and explaining it in real time.

2. **A ready-to-run tunnel resync script** (`scripts/resync_tunnel_url.py`) — automatically reads whatever URL ngrok is currently using and pushes it into ServiceNow's `webhook.url` property, removing the manual copy-paste step that has caused mismatches before. Run this immediately after starting ngrok, every time, including on presentation day.

---

## Scenario 1 — Internet/Wi-Fi drops during the live demo

**What we see:** ServiceNow won't load, or the webhook never arrives because our machine has no connectivity.

**What we do, live, in the room:**
1. Acknowledge it openly to the audience — "looks like we've lost connectivity, let's switch to the completed run" — rather than stalling silently.
2. Open the **pre-staged mocked incident** (see readiness item above) and continue the story arc from there — showing the real final state, the AI's reasoning, sources, and the approval action — fully live navigation, not a recording.
3. If connectivity returns within a minute or two, optionally return to a fresh live run to close out strong.

## Scenario 2 — ngrok tunnel breaks or webhook stops reaching the backend

**What we see:** Incident is created in ServiceNow, but AI fields never update — the same symptom as the `.dev`/`.app` URL mismatch we hit during testing.

**What we do, live, in the room:**
1. Switch to a second terminal (kept open and ready throughout the demo) and run `python scripts/resync_tunnel_url.py` — this takes a few seconds and resolves the single most common cause of this failure automatically.
2. Re-trigger the same incident (or create a new one) once resynced, and continue live.
3. If this doesn't resolve it within ~30 seconds, fall back to the manual webhook script (Scenario 3) to keep the demo moving rather than troubleshooting live for an extended period.

## Scenario 3 — ServiceNow itself is unreachable (outage, login failure, PDI down)

**What we see:** ServiceNow won't load at all, independent of our own network — meaning the whole front half of the pipeline is unavailable, but our backend (FastAPI/Celery/Qdrant/LLM) may still be running fine.

**What we do, live, in the room — non-video recovery:**
1. Run the prepared fallback script: `python scripts/manual_webhook_send.py`. This manually constructs and signs a real event payload (identical in shape and signature method to what ServiceNow would normally send) and POSTs it directly to our running FastAPI receiver — **bypassing ServiceNow entirely**.
2. Narrate this live to the audience as what's actually happening: "Normally ServiceNow sends this signed event — since it's unreachable right now, I'm going to send the exact same kind of signed request myself, so you can see the rest of the pipeline — verification, retrieval, the AI's reasoning — still working live."
3. Show the Celery worker terminal processing it in real time, and the final generated recommendation printed to the terminal/logs (since writeback to ServiceNow won't be visible if ServiceNow is down, the recommendation output itself becomes the live proof).
4. This demonstrates the actual engineering — signature verification, dedup, retrieval, LLM reasoning — is real and working, independent of ServiceNow's availability, entirely live and unscripted.

---

## Rehearsal Checklist (completed with the team before presentation day)

- [ ] Pre-staged mocked incident created and verified complete in ServiceNow
- [ ] `resync_tunnel_url.py` tested against a live ngrok session
- [ ] `manual_webhook_send.py` tested end-to-end against the live backend, with `FALLBACK_INCIDENT_SYS_ID`/`FALLBACK_INCIDENT_NUMBER` env vars set to the mocked incident's real values
- [ ] All three scenarios rehearsed at least once as a team, with someone timing how long each recovery actually takes
- [ ] Both fallback scripts committed to the repo and confirmed runnable from a clean terminal (no missing env vars)
