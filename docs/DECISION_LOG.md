# Decision Log

This log records consequential choices that can be verified from the merged implementation and the S4.2 evaluation. It does not claim to be a contemporaneous, author-approved ADR history; where intent is not explicit in code, the operational justification is identified as an interpretation.

## Runtime and integration

| Decision | Operational justification | Trade-off / current caveat |
|---|---|---|
| Authenticate webhooks with HMAC-SHA256 over raw request bytes before JSON parsing. | Reject modified/forged requests and ensure the signed bytes are the bytes interpreted. | The signature has no timestamp/nonce; replay suppression depends on Redis TTL and identifier selection. |
| Return a fast accepted response and dispatch long-running work through Celery/Redis. | Keep model inference and external API latency out of normal event processing. | Receiver still makes a synchronous best-effort ServiceNow claim before it responds; dispatch failures are not automatically retried by the sender. |
| Use Redis `SET NX EX` as the event de-duplication gate. | Atomic duplicate suppression with bounded key retention. | 24-hour TTL; KB events deduplicate by article ID and can skip legitimate follow-on events. |
| Use a bounded tool-calling agent with two terminal outcomes: `suggestAnswer` or `requestHR`. | Bound execution and ensure a human-reviewable suggestion or escalation is the intended endpoint. | No tool can resolve/close/reassign; the requestHR name does not represent an HR integration. |
| Require cited sources returned by `searchKB` in the current run; set `human_review_required`. | Constrain suggestions to retrieved evidence and keep a human in the decision loop. | Confidence is self-assessed by the model and is not calibrated. |
| Retrieve the top five dense Qdrant chunks without a score cutoff or reranker. | Keep retrieval implementation simple and let the agent assess evidence sufficiency. | Weak and adjacent results can reach the model; refusal decisions are model-dependent. |
| Use the `kb_articles` Qdrant collection and Gemini `gemini-embedding-2` (3072 dimensions). | Share one retrieval index between ingested KB material and PDF chunks with compatible vector dimensions. | Retriever collection is hard-coded even though ingestion has a collection setting; changing embedding dimensions requires re-ingestion. |
| Keep PDF ingestion as a manual CLI separate from the live webhook path. | Allows selected manuals to be converted/loaded without coupling expensive vision processing to incident events. | Ingestion is slow/cost-bearing and corpus freshness is not automatic. |
| Write status/suggestion/escalation to ServiceNow and ignore Celery task results. | ServiceNow is the operational record and human-review surface. | Failures have no automated re-drive. Receiver and worker both attempt incident claim in the current implementation. |

## Quality evaluation

| Decision | Operational justification | Trade-off / interpretation |
|---|---|---|
| Exercise the real agent and real retrieval, while replacing ServiceNow writeback with a capture-only stub. | Measure the deployed reasoning/retrieval path without modifying incidents during evaluation. | Requires live LLM, Gemini and Qdrant access; output is model-dependent. |
| Include 87 answerable, 12 refusal and 1 clarification turns. | Measure grounded answering and whether unsupported questions are refused/escalated instead of hallucinated. | The agent has no clarification tool; clarification is mapped to `requestHR`. |
| Wrap dataset questions as inquiry incidents and use standalone input by default. | Match the incident-shaped production interface without introducing assumed conversational memory. | The system has no history/query rewriting; standalone mode does not test multi-turn coreference. |
| Score retrieved chunks by token containment with per-case reference contexts. | The dataset's numbered section IDs do not align with the `page_N_*` metadata on some ingested PDF chunks. | Reference recall/precision and forbidden-section checks are heuristic, not exact corpus-ID matches. |
| Apply metric thresholds and route checks per case, skipping answer metrics when an answerable turn is escalated. | Treat over-refusal as a route failure once rather than repeatedly failing metrics on a missing answer. | Aggregate pass rate reflects a mixed deterministic/LLM-judge rubric, not a production SLA. |
| Use a capture-only ServiceNow client for evaluation. | Ensure the harness cannot modify a live incident. | Evaluation pass does not verify end-to-end ServiceNow deployment or writeback permissions. |
| Redact configured secret values and scan generated evaluation artifacts. | Reduce the chance that a run artifact exposes credentials. | Scanner coverage is limited to known values; manual review remains required. |

## Findings from the recorded evaluation

The full run `20261001T150304Z` is the basis for the current report. It completed both retrieval and agent stages for 100 cases with no judge errors, but it is not an all-clear: turn pass rate was 0.38; route accuracy was 0.67; 31 of 87 answerable turns were escalated and one had no terminal outcome; 12 of 13 refusal/clarification cases were routed to escalation. See the [full report](../evaluation/results/20261001T150304Z/summary.md) and [evaluation guide](../evaluation/README.md) for metric scores, test cases and limitations.

The dataset declares corpus `BARQ_IT_Service_Desk_Manual_Ed5.docx` and edition `4.0`. Retrieved chunks in this run identify themselves as the *BARQ Systems IT Service Operations Manual*, Edition 4.0, with a `52 of 52` footer. The name mismatch is unresolved; the run confirms material was retrieved but does not prove that the dataset's intended full corpus and references match the indexed source. Recall/precision use text-containment heuristics. Avoid presenting the run as a direct measure of all deployed content or as proof of production readiness.
