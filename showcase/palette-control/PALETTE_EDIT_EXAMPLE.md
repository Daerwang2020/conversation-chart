# Palette Control Example

This showcase demonstrates a controllable multi-round edit that only changes color plan:

- Round-001: `color-plan.json` v1 (category colors)
- Round-002: `color-plan.json` v2 (same categories, different palette)

Workflow:

1. Keep `chart.dsl.json` as structural source.
2. Let skill/LLM output `color-plan.json`.
3. Run `run_local_pipeline.py` with `spec.color_plan`.
4. Pipeline generates `chart.colored.dsl.json` and renders from it.

Guarantees:

- Node/edge/group IDs stay unchanged
- Geometry and routing remain stable unless explicitly edited
- Source-to-visual mapping is re-exported in each round
