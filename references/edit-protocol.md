# Edit Protocol

## Principles

- Edit by stable ID first.
- Keep IDs immutable once created.
- Keep one source of truth per round: `chart.dsl.json`.
- Write explicit round delta in `changes.json`.

## Supported Round Operations

1. Add/update/remove node
- Mutable fields: `label`, `x`, `y`, `width`, `height`, `shape`, `style`

2. Add/update/remove edge
- Mutable fields: `from`, `to`, `label`, `relation`, `style`, `waypoints`

3. Group topology changes
- Add/update/remove `groups`
- Update group membership by node IDs only

4. Theme-level controlled update
- Update top-level `theme`
- Use for global palette switching without renaming IDs
- Preferred fields for palette control: `theme.color_mode`, `theme.category_source`, `theme.category_colors`, `theme.category_assignments`, `theme.node_cycle`, `theme.background`

5. Color-plan controlled update (recommended)
- Keep structural DSL unchanged
- Update `color-plan.json` only: `category_assignments`, `category_colors`, `theme_overrides`
- Re-run pipeline with `spec.color_plan`

## Controlled Architecture Upgrade Pattern

For upgrades like classic RAG -> improved RAG:

- Keep existing IDs for persistent modules
- Add new capability nodes with new IDs
- Prefer updating existing edge IDs when semantics evolve
- Only use `removed` when element truly disappears

For palette-only rounds:

- Keep `nodes/edges/groups` unchanged
- Update `color-plan.json` (`category_colors` or `category_assignments`) only
- Re-render and re-export mapping to keep source-visual traceability

## Target Resolution Order

1. Exact ID match
2. Unique exact label match
3. Unique case-insensitive label match
4. Ambiguous target -> no mutation + warning

## Routing and Occlusion Rules

- Prefer `route=orthogonal` in dense system diagrams
- Keep `avoid_obstacles=true` unless readability demands local override
- For ingress/egress edges, allow `avoid_obstacles=false` if it improves clarity
- Run occlusion analysis every round:
  - `python scripts/analyze_occlusion.py --layout <layout> --output <report> --max-issues 0`

## Round Procedure

1. Load previous `chart.dsl.json`
2. Apply requested structure edits (if any)
3. Save next `chart.dsl.json`
4. Generate/update `color-plan.json` (if color change requested)
5. Run pipeline (auto-apply color plan if `spec.color_plan` exists)
6. Analyze occlusion result
7. Export SVG + TikZ (+mapping)
8. Optionally compile TikZ chain
9. Save `changes.json`

## `changes.json` Requirements

Always include:

- `added`
- `updated`
- `removed`
- `warnings`

Use IDs only in delta arrays (node/edge/group IDs).
