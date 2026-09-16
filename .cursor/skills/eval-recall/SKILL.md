---
name: eval-recall
description: >-
  Evaluate RAG chunk-level recall@K for enterprise-knowledge-hub and optionally
  write scores to Langfuse. Use when the user asks for recall, 召回率,
  context_recall, retrieval eval, or comparing hybrid_retrieve strategies.
---

# Eval Recall

Offline chunk-ID recall for this repo. Do **not** invent gold labels; require a labeled set.

## Inputs

Eval JSONL (one object per line):

```json
{"id": "q1", "question": "差旅报销需要哪些材料？", "reference_chunk_ids": [12, 45]}
```

- `question` (required)
- `reference_chunk_ids` (required): gold chunk ids that should be retrieved
- Optional: `owner_ids`, `top_k` (default `settings.rag_top_k`)

## Workflow

1. Confirm eval file path and `top_k` (default from `app.core.settings.settings.rag_top_k`).
2. For each item, call:

```python
from app.ai.retrievers.hybrid_retriever import hybrid_retrieve

hits = await hybrid_retrieve(db, question, owner_ids, top_k=top_k)
retrieved_ids = {h.chunk_id for h in hits}
gold = set(reference_chunk_ids)
recall = len(retrieved_ids & gold) / len(gold) if gold else 0.0
hit = 1.0 if (retrieved_ids & gold) else 0.0
```

3. Aggregate mean `recall@K` and `hit@K` across the set.
4. Report per-item misses: gold ids not in `retrieved_ids`.

## Langfuse (optional)

Only if `settings.langfuse_enabled` and keys are set:

1. Create a trace/span named `eval.recall` with input `{question, top_k}`.
2. Attach scores:

```python
langfuse.create_score(name="context_recall", value=recall, trace_id=trace_id)
langfuse.create_score(name="hit_rate", value=hit, trace_id=trace_id)
```

3. Prefer ID-based recall here; do not pull in Ragas unless the user explicitly asks.

## Related code

- Retrieval: `app/ai/retrievers/hybrid_retriever.py` (already logs `bm25_ids` / `vector_ids` / `rerank_ids`)
- Settings: `rag_top_k`, `recall_top_k`, Langfuse flags in `app/core/settings.py`
- Observability: `app/observability/langfuse_client.py`

## Output format

```markdown
## Recall@K summary
- items: N
- top_k: K
- mean recall@K: 0.xx
- mean hit@K: 0.xx

## Misses
- q1: missing chunk_ids [...]
```

## Do not

- Score production chat without gold labels
- Treat "number of chunks returned" as recall
- Modify retrieval code unless the user asks to improve recall after seeing results
