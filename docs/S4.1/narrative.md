# Sprint 4.1 — Demo Narrative & Presentation Story Arc

**Project:** BARQ G3 — AI ServiceNow Support Assistant

---

## The Story We're Telling

Every day, IT support teams receive tickets they've effectively already solved before — the same VPN error, the same mail client crash, the same password reset — but a human still has to read the ticket, search for the right documentation, and type up the fix every single time. That repetition is where this project lives: **BARQ watches for new IT support tickets, automatically finds the right documented fix, and drafts the resolution — so a human reviewer just has to check it and approve, instead of starting from a blank page.**

This isn't "an AI that answers anything." It only ever speaks when it has found real, matching documentation to back it up — and when it can't find anything relevant, it says so honestly instead of guessing. That honesty is the core trust story of the whole demo.

---

## The Four-Act Flow

### Act 1 — A ticket comes in
A user reports a real IT problem in ServiceNow — in our verified run, an incident about Outlook disconnecting from the mail server. The moment it's saved, the system notices it's a fresh, unprocessed ticket and quietly announces it to the AI backend, carrying a tamper-proof digital signature so the backend can trust the message really came from ServiceNow and wasn't altered in transit.

*(For the room: think of this like a sealed, signed envelope — anyone could technically intercept it, but they can't forge it or open and change it without the seal breaking.)*

### Act 2 — The backend picks it up
A receiving service checks that seal, makes sure this exact ticket hasn't already been handled (so nothing gets processed twice), and hands it off to a background worker — instantly, without making the person who filed the ticket wait.

### Act 3 — The AI investigates
The background worker does what a good Tier-1 support agent would do: it searches the company's own knowledge base for anything relevant, reads what it finds, and only then drafts a resolution — citing exactly which document it pulled each step from. In our verified run, it found the right article, proposed a clear 5-step fix, and rated its own confidence in that answer.

### Act 4 — A human stays in the loop
The draft resolution is written back into the ticket — but it doesn't close the ticket or act on its own. A human support agent opens it, reads the AI's reasoning and sources, and clicks **Approve** before anything is finalized. The AI drafts; the human decides.

---

## Live-Run Evidence Anchoring This Story

*(Used to build S4.4 slides and the S4.5 demo video — do not re-word these facts when producing those, re-derive the framing instead.)*

| Checkpoint | What to show | Evidence source |
|---|---|---|
| Act 1 | Incident created in ServiceNow, signed webhook sent | Incident record + ngrok inspector (`127.0.0.1:4040`) capture showing `X-Signature` header and JSON body |
| Act 2 | Signature verified, event queued | FastAPI/Celery terminal logs showing `202 Accepted` and task pickup |
| Act 3 | Agent reasoning visible | Celery worker terminal log showing tool calls (`searchKB`, etc.) and retrieved sources |
| Act 4 | Final state + human approval | Incident's five AI fields in final state (`ai_status`, `ai_processed`, `ai_confidence`, `ai_suggested_response`, `human_review_required`) + screenshot of Approve action |

**Reference incident:** see the committed End-to-End Test Document for the exact `sys_id`, field values, and incident text used as canonical proof.

---

## Technical Reference Layer (for Q&A / technical audience members)

This section is the detail underneath the story above — use it if asked "how does that actually work," not as the opening pitch.

- **Transport & security:** ServiceNow Async Business Rule → HMAC-SHA256 signed JSON POST → ngrok tunnel → FastAPI. Signature computed over the exact stringified request body; secret and target URL are read from scoped ServiceNow system properties, never hardcoded.
- **Reliability:** Async rule execution means the ServiceNow user's save is never blocked waiting on an external HTTP call. Redis-based deduplication on the webhook's `event_id` prevents duplicate processing from retries.
- **Processing:** FastAPI enqueues to Celery (Redis-backed) rather than processing inline, decoupling slow AI work from the fast webhook acknowledgment.
- **AI grounding:** Retrieval-augmented generation against a Qdrant vector store of ingested KB articles. The agent is prompted to treat incident text as untrusted input and to decline rather than hallucinate when no relevant KB content is retrieved — this is enforced by a deterministic guard, not left purely to model behavior.
- **Human-in-the-loop:** The agent never auto-closes a ticket; it writes a suggested resolution and confidence score, and a human must explicitly approve via a ServiceNow UI Action before the resolution is finalized.

---

## Presenting to a Mixed Room — Delivery Notes

- Open with the *problem* (repetitive ticket triage), not the architecture diagram.
- Show the live ticket text and the AI's final suggestion side-by-side before explaining any plumbing — let the output speak first.
- When a technical question comes up, answer it, then return to the story arc rather than staying in the technical weeds.
- Close on the human-approval step — it's the strongest trust signal for a non-technical stakeholder ("the AI doesn't act alone").
