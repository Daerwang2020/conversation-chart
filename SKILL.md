---
name: conversation-chart
description: Generate and iteratively edit conversation charts as PNG diagrams including flowcharts, data flow diagrams, information block diagrams, and complex interaction relationship graphs. Use when users ask to draw or revise diagram structures in multiple rounds and require stable source-to-visual traceability with local file/script outputs.
---

# Conversation Chart

## Objective
- Produce publication-ready diagram artifacts from local files.
- Keep stable ID mapping between source and visual output.
- Support multi-round controlled edits.
- Prevent text/edge/frame occlusion as a required quality gate.

## Required Local Interface (Mandatory)
Use a local file + script pipeline:
- Input: `input.md` + `spec.json`
- Source graph: `chart.dsl.json`
- Optional plan input: `color-plan.json` (LLM generated)
- Output: `output.png`, `output.layout.json`, `output.occlusion.json`, `output.map.json`, `output.svg`, `output.tex` (and optional `output.pdf`)
- Scripts:
  - `scripts/run_local_pipeline.py`
  - `scripts/apply_color_plan.py`
  - `scripts/render_png.py`
  - `scripts/render_svg.py`
  - `scripts/render_tikz.py`
  - `scripts/render_tikz_chain.py`
  - `scripts/analyze_occlusion.py`

## Execution Workflow
1. Resolve `spec.json` and load `input.md` context if provided.
2. If `spec.color_plan` exists, merge plan into DSL:
   - `python scripts/apply_color_plan.py --dsl <chart.dsl.json> --plan <color-plan.json> --output <chart.colored.dsl.json>`
3. Render PNG + layout:
   - `python scripts/render_png.py --input <dsl> --png <output.png> --layout <output.layout.json>`
4. Run occlusion analysis:
   - `python scripts/analyze_occlusion.py --layout <output.layout.json> --output <output.occlusion.json> --max-issues 0`
5. Export SVG:
   - `python scripts/render_svg.py --source <dsl> --layout <output.layout.json> --output <output.svg>`
6. Export TikZ:
   - `python scripts/render_tikz.py --source <dsl> --layout <output.layout.json> --output <output.tex>`
7. Optional compile chain:
   - `python scripts/render_tikz_chain.py --tex <output.tex> --output-dir <dir> --basename <name>`
8. Write mapping and round delta (`chart.map.json`, `changes.json`) when doing iterative edits.

## Quality Rules
- IDs must remain stable across rounds.
- Prefer orthogonal obstacle-avoid routing for dense graphs.
- Edge labels must avoid occluding node text whenever possible.
- Keep `occlusion.issue_count <= max_occlusion_issues`.

## LLM Color Planning (Category-based)
Color assignment logic should be planned by the skill/LLM, not hardcoded in renderer code.

LLM should output `color-plan.json` with category mapping + palette:

```json
{
  "color_mode": "category",
  "category_source": "group",
  "category_assignments": {
    "n_user": "access",
    "n_gateway": "access",
    "n_retriever": "retrieval"
  },
  "category_colors": {
    "access": "#56B4E9",
    "retrieval": "#009E73",
    "generation": "#E69F00",
    "ops": "#CC79A7"
  },
  "theme_overrides": {
    "background": "#F8FAFC",
    "edge_color": "#475569",
    "node_border": "#1E293B",
    "node_text": "#0F172A"
  }
}
```

Renderer responsibilities:
- Apply `theme.category_assignments` + `theme.category_colors` deterministically
- Keep explicit `node.style.fill` as highest priority override
- Keep source-to-visual mapping stable across rounds
- Select palette candidates from `references/color-presets.md` (web-curated sources)

## Style Profile (English, Default)
Use this style profile as the default visual baseline:

- `references/style-profiles/clean-rounded-v1.json`

Profile intent:
- clean and linear layout
- rounded corners as primary shape language
- category-based color assignment (same category, same color)
- high legibility for README architecture diagrams

When users ask for "clean / linear / rounded" style, prioritize this profile unless they explicitly override it.

## Notes
- Position this skill as a paper-figure skill, not a TikZ-only skill.
- TikZ is an internal high-quality backend, SVG is compatibility backend.

## References
- `references/output-contract.md`
- `references/edit-protocol.md`
- `references/color-presets.md`
- `references/style-profiles/clean-rounded-v1.json`
