# Controllable Edit Example: Classic RAG -> Improved RAG

## Goal
Show a controlled multi-round edit that keeps stable IDs and performs two explicit modifications:

1. Change theme colors globally.
2. Upgrade architecture from classic RAG to improved RAG.

## Round 1
- File: `round-001/chart.dsl.json`
- Style: baseline light theme.
- Architecture: rewrite + hybrid retrieval + reranker + guardrails.

## Round 2 (Controlled Edit)
- File: `round-002/chart.dsl.json`
- Theme change:
  - updated via top-level `theme` values
  - node/group colors updated to stronger contrast palette
- Architecture upgrade:
  - add `n_router` (query routing)
  - add `n_hyde` (synthetic document guidance)
  - add `n_graph` (GraphRAG retrieval source)
  - add `n_judge` (groundedness judge feedback loop)

## Stable-ID Rule Demonstrated
- Existing IDs keep their original names.
- New functionality appears as additive IDs.
- Relations are evolved via edge updates and new edges.

## Suggested Edit Prompt

"From the current classic RAG graph, keep all existing IDs. Apply a dark-neutral theme with higher contrast. Add query routing, HyDE generation, GraphRAG retrieval, and groundedness judge feedback loop. Keep output format as PNG + dsl + layout + map + changes."
