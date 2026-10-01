# Sprint 4.1 Narrative & Demo Story Arc

**Project:** BARQ G3 — AI ServiceNow Support Assistant  

---

## Story Arc: End-to-End Autonomous Support Flow

### Phase 1: Incident Creation & Outbound Webhook Trigger
An IT end-user submits an incident (`INC0010116`) reporting an Outlook disconnection issue. ServiceNow's asynchronous Business Rule (`Outbound Webhook - Incident Events`) intercepts the record insertion, constructs an HMAC-SHA256 signed JSON payload using secret key validation, and dispatches a POST request to the application gateway via ngrok.

### Phase 2: Gateway Verification & Asynchronous Queueing
FastAPI receives the inbound request, verifies the `X-Signature` HMAC header against local settings to guarantee message authenticity, enforces idempotency via Redis deduplication, and hands off the payload asynchronously to a Celery worker.

### Phase 3: RAG Retrieval & LangGraph Execution
The Celery worker triggers the LangGraph agent execution pipeline:
1. **Context Retrieval:** Queries the Qdrant vector database for relevant Knowledge Base articles (`KB0010003`).
2. **Analysis & Resolution Generation:** The LLM generates a structured 5-step diagnostic and remediation guide with high confidence (`0.9`).
3. **Threshold Guardrail Check:** Because human review is enabled, `human_review_required` is evaluated to `true`.

### Phase 4: ServiceNow Response Writeback & Human Approval
The backend issues a authenticated REST call back to ServiceNow, setting `ai_status` to `suggested`, `ai_processed` to `true`, and attaching the step-by-step guidance. The IT helpdesk agent opens `INC0010116`, reviews the AI recommendation, and clicks **Approve AI Suggestion** to post the work notes and resolve the incident.