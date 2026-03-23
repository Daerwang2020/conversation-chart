#!/usr/bin/env python3
"""Render SVG from chart.dsl.json + chart.layout.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple
from xml.sax.saxutils import escape


Point = Tuple[int, int]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render SVG from chart DSL and layout")
    parser.add_argument("--source", required=True, help="Path to chart.dsl.json")
    parser.add_argument("--layout", required=True, help="Path to chart.layout.json")
    parser.add_argument("--output", required=True, help="Path to output.svg")
    return parser.parse_args()


def hex_or_default(value: str | None, default: str) -> str:
    if not value:
        return default
    text = value.strip()
    if text.startswith("#") and len(text) in {7, 9}:
        return text[:7]
    return default


def parse_node_cycle(raw: object) -> List[str]:
    colors: List[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                c = hex_or_default(item, "")
                if c:
                    colors.append(c)
    return colors


def normalized_key(text: str) -> str:
    return text.strip().lower().replace(" ", "_")


def parse_category_colors(raw: object) -> Dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    result: Dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        cat = normalized_key(key)
        color = hex_or_default(value, "")
        if cat and color:
            result[cat] = color
    return result


def parse_category_assignments(raw: object) -> Dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    result: Dict[str, str] = {}
    for node_id, cat in raw.items():
        if not isinstance(node_id, str) or not isinstance(cat, str):
            continue
        key = normalized_key(cat)
        if key:
            result[node_id] = key
    return result


def build_group_map(raw_groups: object) -> Dict[str, str]:
    if not isinstance(raw_groups, list):
        return {}
    node_to_group: Dict[str, str] = {}
    for group in raw_groups:
        if not isinstance(group, dict):
            continue
        gid = normalized_key(str(group.get("id", "")))
        glabel = normalized_key(str(group.get("label", "")))
        key = gid or glabel
        if not key:
            continue
        for node_id in group.get("nodes", []):
            if isinstance(node_id, str) and node_id not in node_to_group:
                node_to_group[node_id] = key
    return node_to_group


def node_category_color_maps(nodes_raw: List[dict], raw_groups: object, source_theme: dict) -> Tuple[Dict[str, str], Dict[str, str]]:
    color_mode = normalized_key(str(source_theme.get("color_mode", "category")))
    category_source = normalized_key(str(source_theme.get("category_source", "auto")))
    cycle = parse_node_cycle(source_theme.get("node_cycle"))
    category_colors = parse_category_colors(source_theme.get("category_colors"))
    assignments = parse_category_assignments(source_theme.get("category_assignments"))
    group_map = build_group_map(raw_groups)

    node_category: Dict[str, str] = {}
    category_to_color: Dict[str, str] = dict(category_colors)
    next_idx = 0

    for node in nodes_raw:
        node_id = str(node.get("id", ""))
        if not node_id:
            continue

        if color_mode == "node":
            key = normalized_key(node_id)
        else:
            key = assignments.get(node_id)
            if not key:
                node_cat = normalized_key(str(node.get("category", "")))
                if category_source == "node":
                    key = node_cat or normalized_key(node_id)
                elif node_cat:
                    key = node_cat
                elif category_source == "group":
                    key = group_map.get(node_id)
                elif category_source == "none":
                    key = None
                else:  # auto
                    key = group_map.get(node_id)

        if not key:
            continue
        if key not in category_to_color and cycle:
            category_to_color[key] = cycle[next_idx % len(cycle)]
            next_idx += 1
        if key in category_to_color:
            node_category[node_id] = key

    node_colors = {nid: category_to_color[key] for nid, key in node_category.items() if key in category_to_color}
    return (node_colors, node_category)


def contrast_text(fill_hex: str) -> str:
    text = hex_or_default(fill_hex, "#FFFFFF")
    r = int(text[1:3], 16)
    g = int(text[3:5], 16)
    b = int(text[5:7], 16)
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#0F172A" if luma >= 145 else "#F8FAFC"


def parse_points(raw: list[list[int]]) -> List[Point]:
    points: List[Point] = []
    for item in raw:
        if isinstance(item, list) and len(item) == 2:
            points.append((int(item[0]), int(item[1])))
    return points


def wrap_text(label: str, max_chars: int = 24) -> List[str]:
    words = label.strip().split()
    if not words:
        return []
    lines: List[str] = []
    cur = ""
    for w in words:
        p = w if not cur else f"{cur} {w}"
        if len(p) > max_chars and cur:
            lines.append(cur)
            cur = w
        else:
            cur = p
    if cur:
        lines.append(cur)
    return lines[:4]


def main() -> int:
    args = parse_args()
    source_path = Path(args.source)
    layout_path = Path(args.layout)
    output_path = Path(args.output)

    with source_path.open("r", encoding="utf-8-sig") as f:
        source = json.load(f)
    with layout_path.open("r", encoding="utf-8-sig") as f:
        layout = json.load(f)

    canvas = layout.get("canvas", {})
    width = int(canvas.get("width", 1200))
    height = int(canvas.get("height", 700))
    bg = hex_or_default(canvas.get("background"), "#FFFFFF")
    source_theme = source.get("theme", {}) if isinstance(source.get("theme", {}), dict) else {}
    theme_node_fill = hex_or_default(source_theme.get("node_fill"), "#FFFFFF")
    theme_node_border = hex_or_default(source_theme.get("node_border"), "#1E293B")
    theme_node_text = hex_or_default(source_theme.get("node_text"), "#0F172A")

    nodes_raw = source.get("nodes", []) if isinstance(source.get("nodes", []), list) else []
    nodes_by_id: Dict[str, dict] = {str(n.get("id", "")): n for n in nodes_raw}
    node_color_by_id, _ = node_category_color_maps(nodes_raw, source.get("groups", []), source_theme)
    edges_by_id: Dict[str, dict] = {str(e.get("id", "")): e for e in source.get("edges", [])}

    parts: List[str] = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">'
    )
    parts.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="{bg}"/>')
    parts.append("<defs>")
    parts.append(
        '<marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">'
        '<path d="M0,0 L10,4 L0,8 Z" fill="#334155"/></marker>'
    )
    parts.append("</defs>")

    for group in layout.get("groups", []):
        bbox = group.get("bbox_px")
        if not bbox or len(bbox) != 4:
            continue
        gx, gy, gw, gh = [int(v) for v in bbox]
        style = group.get("style", {})
        fill = hex_or_default(style.get("fill"), "#FFFFFF")
        stroke = hex_or_default(style.get("stroke"), "#94A3B8")
        label = escape(str(group.get("label", "")))
        parts.append(
            f'<rect x="{gx}" y="{gy}" width="{gw}" height="{gh}" rx="18" ry="18" '
            f'fill="{fill}" fill-opacity="0.18" stroke="{stroke}" stroke-width="2"/>'
        )
        if label:
            parts.append(f'<text x="{gx + 10}" y="{gy + 20}" fill="{stroke}" font-size="14" font-family="Segoe UI">{label}</text>')

    for edge in layout.get("edges", []):
        edge_id = str(edge.get("id", ""))
        src_edge = edges_by_id.get(edge_id, {})
        style = edge.get("style", {})
        color = hex_or_default(style.get("color"), "#475569")
        route_points = parse_points(edge.get("polyline_px", []))
        if len(route_points) < 2:
            continue
        d = " M ".join(f"{x},{y}" for x, y in route_points)
        pattern = str(style.get("pattern", "solid"))
        dash = ""
        if pattern == "dashed":
            dash = ' stroke-dasharray="12 8"'
        elif pattern == "dotted":
            dash = ' stroke-dasharray="2 8"'
        direction = str(style.get("direction", "single"))
        marker_end = ' marker-end="url(#arrow)"' if direction in {"single", "both"} else ""
        marker_start = ' marker-start="url(#arrow)"' if direction == "both" else ""
        width_px = int(style.get("width", 3))
        parts.append(
            f'<path d="M {d}" fill="none" stroke="{color}" stroke-width="{width_px}"{dash}{marker_start}{marker_end}/>'
        )

        label = escape(str(src_edge.get("label", edge.get("label", ""))))
        lb = edge.get("label_bbox_px")
        if label and lb and len(lb) == 4:
            lx, ly, lw, lh = [int(v) for v in lb]
            parts.append(
                f'<rect x="{lx}" y="{ly}" width="{lw}" height="{lh}" rx="8" ry="8" '
                f'fill="#FFFFFF" fill-opacity="0.86" stroke="#CBD5E1" stroke-width="1"/>'
            )
            parts.append(f'<text x="{lx + 8}" y="{ly + 16}" fill="#1F2937" font-size="12" font-family="Segoe UI">{label}</text>')

    for node in layout.get("nodes", []):
        node_id = str(node.get("id", ""))
        src_node = nodes_by_id.get(node_id, {})
        style = src_node.get("style", {}) if isinstance(src_node.get("style", {}), dict) else {}
        category_fill = node_color_by_id.get(node_id)
        fill = hex_or_default(style.get("fill") or category_fill, theme_node_fill)
        stroke = hex_or_default(style.get("stroke"), theme_node_border)
        text_color = hex_or_default(style.get("text"), contrast_text(fill) if category_fill and not style.get("text") else theme_node_text)

        bbox = node.get("bbox_px", [])
        if len(bbox) != 4:
            continue
        x, y, w, h = [int(v) for v in bbox]
        shape = str(node.get("shape", "rounded")).lower()
        if shape == "ellipse":
            parts.append(
                f'<ellipse cx="{x + w // 2}" cy="{y + h // 2}" rx="{w // 2}" ry="{h // 2}" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
            )
        else:
            rx = h // 2 if shape == "pill" else 14
            parts.append(
                f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" ry="{rx}" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
            )

        label = escape(str(src_node.get("label", node.get("label", ""))))
        lines = wrap_text(label)
        if lines:
            base_y = y + (h - (len(lines) * 18)) // 2 + 14
            for i, line in enumerate(lines):
                parts.append(
                    f'<text x="{x + w // 2}" y="{base_y + i * 18}" text-anchor="middle" '
                    f'fill="{text_color}" font-size="15" font-family="Segoe UI">{line}</text>'
                )

    parts.append("</svg>")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(parts))
        f.write("\n")

    print(f"[render_svg] source={source_path}")
    print(f"[render_svg] layout={layout_path}")
    print(f"[render_svg] output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
