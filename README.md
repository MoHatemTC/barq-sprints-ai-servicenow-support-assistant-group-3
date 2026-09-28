## Confidence Score

The `confidence` value is an LLM-assigned heuristic score between 0.0 and 1.0.

It is based on:
- How directly the retrieved KB evidence addresses the incident.
- Whether the retrieved evidence provides a concrete resolution procedure.
- Whether all proposed resolution steps are supported by the retrieved KB content.
- Whether any important part of the incident remains unsupported.

The score is validated by the `SuggestAnswerInput` schema and must be within
the range `0.0 <= confidence <= 1.0`.

The confidence score is not:
- A calibrated probability of correctness.
- A direct Qdrant similarity score.
- Computed mathematically from the retrieval score.

For example, a Qdrant similarity score of `0.72` does not mean the agent
confidence must be `0.72`. The LLM evaluates the retrieved evidence and
assigns the final heuristic confidence used by `suggestAnswer`.

```
uv sync
cp .env.example .env      # fill in QDRANT_*, GEMINI_API_KEY, LLM_*
uv run pytest             # offline tests; live-Qdrant tests skip automatically
```

## Sprints

| Sprint | Scope | Owner |
|---|---|---|
| S2.1 | Chunking, embedding, Qdrant storage | Malak |
| S2.2 | Semantic retrieval + threshold gate | Aliaa |
| S2.3 | Agent tool schemas (no resolve/close/reassign) | team |
| S2.4 | Agent reasoning + grounded generation | Dana |
| S2.5 | Retrieval benchmark & threshold evaluation | Ashar |
