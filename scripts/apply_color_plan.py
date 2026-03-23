#!/usr/bin/env python3
"""Apply LLM-generated color plan onto chart DSL.

This script is deterministic by design: it only merges provided fields and does
not infer categories or colors on its own.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply color-plan.json to chart.dsl.json")
    parser.add_argument("--dsl", required=True, help="Path to source chart.dsl.json")
    parser.add_argument("--plan", required=True, help="Path to color-plan.json")
    parser.add_argument("--output", required=True, help="Path to output chart.dsl.json")
    return parser.parse_args()


def normalize_hex(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip().upper()
    if not text.startswith("#"):
        return None
    if len(text) == 7:
        return text
    if len(text) == 9:
        return text[:7]
    return None


def normalize_key(text: str) -> str:
    return text.strip().lower().replace(" ", "_")


def normalize_category_colors(raw: object) -> Dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, str] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        key = normalize_key(k)
        color = normalize_hex(v)
        if key and color:
            out[key] = color
    return out


def normalize_category_assignments(raw: object) -> Dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, str] = {}
    for node_id, cat in raw.items():
        if not isinstance(node_id, str) or not isinstance(cat, str):
            continue
        key = normalize_key(cat)
        if key:
            out[node_id] = key
    return out


def normalize_cycle(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            c = normalize_hex(item)
            if c:
                out.append(c)
    return out


def main() -> int:
    args = parse_args()
    dsl_path = Path(args.dsl)
    plan_path = Path(args.plan)
    out_path = Path(args.output)

    with dsl_path.open("r", encoding="utf-8-sig") as f:
        dsl = json.load(f)
    with plan_path.open("r", encoding="utf-8-sig") as f:
        plan = json.load(f)

    if not isinstance(dsl, dict):
        raise ValueError("Invalid DSL JSON root")
    if not isinstance(plan, dict):
        raise ValueError("Invalid color plan JSON root")

    theme = dsl.get("theme", {})
    if not isinstance(theme, dict):
        theme = {}

    color_mode = str(plan.get("color_mode", theme.get("color_mode", "category")))
    category_source = str(plan.get("category_source", theme.get("category_source", "auto")))
    category_colors = normalize_category_colors(plan.get("category_colors"))
    category_assignments = normalize_category_assignments(plan.get("category_assignments"))
    node_cycle = normalize_cycle(plan.get("node_cycle"))

    theme["color_mode"] = color_mode
    theme["category_source"] = category_source
    if category_colors:
        theme["category_colors"] = category_colors
    if category_assignments:
        theme["category_assignments"] = category_assignments
    if node_cycle:
        theme["node_cycle"] = node_cycle

    theme_overrides = plan.get("theme_overrides", {})
    if isinstance(theme_overrides, dict):
        for key, value in theme_overrides.items():
            if isinstance(key, str) and isinstance(value, str):
                theme[key] = value

    dsl["theme"] = theme

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(dsl, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"[apply_color_plan] dsl={dsl_path}")
    print(f"[apply_color_plan] plan={plan_path}")
    print(f"[apply_color_plan] output={out_path}")
    print(f"[apply_color_plan] category_colors={len(theme.get('category_colors', {}))} assignments={len(theme.get('category_assignments', {}))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
