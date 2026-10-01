# System Fallback & Recovery Plan

**Project:** BARQ G3 — AI ServiceNow Support Assistant  

---

## Failure Scenario 1: Webhook Delivery or Network Tunnel Timeout

* **Failure Mode:** Webhook receiver endpoint fails to respond (5xx status) or ngrok tunnel drops due to network disconnection.
* **Impact:** Incident creation events are not processed by the AI backend; AI fields remain unset (`ai_processed = false`).
* **Recovery Procedure (Operational):**
  1. ServiceNow Business Rules execute asynchronously and log failed POST attempts to System Logs (`syslog`).
  2. IT Helpdesk Agents continue standard manual triage for newly opened incidents without disruption.
  3. Support engineers restart the ngrok/FastAPI container service and run a manual retry script against unprocessed incidents (`ai_processed=false` and `sys_created_on >= target_time`).

---

## Failure Scenario 2: Redis / Celery Task Queue Worker Crash

* **Failure Mode:** The Celery worker process terminates unexpectedly, or Redis cache becomes unreachable.
* **Impact:** Webhook requests are received and verified by FastAPI with `202 Accepted`, but downstream LLM agent analysis halts in queue.
* **Recovery Procedure (Operational):**
  1. FastAPI returns immediate acknowledgment and buffers event payloads in persistent queue storage where available.
  2. Health-check endpoint `/health` alerts monitoring service of Celery process absence.
  3. Automated supervisor (e.g., Docker restart policy or systemd service) restarts the Celery process with `--pool=solo`. Upon startup, Celery reconnects to Redis and resumes consuming buffered tasks automatically without duplicate execution.

---

## Failure Scenario 3: Vector Store (Qdrant) or LLM API Outage / High Latency

* **Failure Mode:** External LLM API returns rate limit (429), server error (500), or Qdrant vector search times out.
* **Impact:** Agent pipeline fails during RAG retrieval or response generation.
* **Recovery Procedure (Operational):**
  1. The agent workflow catches API connection/timeout exceptions gracefully.
  2. Fallback logic sets `ai_status = 'failed'` or `human_review_required = true` with a fallback response: *"Automated triage unavailable. Routed to human agent."*
  3. ServiceNow workflow re-assigns the incident to standard Tier 1 helpdesk assignment group so service SLAs are maintained.