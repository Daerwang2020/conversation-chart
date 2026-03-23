#!/usr/bin/env python3
"""Render TikZ/LaTeX source from chart.dsl.json + chart.layout.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple


Point = Tuple[int, int]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render TikZ from chart DSL and layout")
    parser.add_argument("--source", required=True, help="Path to chart.dsl.json")
    parser.add_argument("--layout", required=True, help="Path to chart.layout.json")
    parser.add_argument("--output", required=True, help="Path to output.tex")
    return parser.parse_args()


def hex_to_tikz_rgb(value: str | None, default: str = "#334155") -> str:
    text = (value or default).strip()
    if not text.startswith("#") or len(text) not in {7, 9}:
        text = default
    text = text[1:7]
    r = int(text[0:2], 16)
    g = int(text[2:4], 16)
    b = int(text[4:6], 16)
    return f"{{rgb,255:red,{r};green,{g};blue,{b}}}"


def hex_or_default(value: str | None, default: str) -> str:
    if not value:
        return default
    text = value.strip()
    if text.startswith("#") and len(text) in {7, 9}:
        return text[:7].upper()
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


def points_to_tikz_path(points: List[Point], scale_y: int) -> str:
    coords = [f"({x},{scale_y - y})" for x, y in points]
    return " -- ".join(coords)


def escape_tex(text: str) -> str:
    repl = {
        "\\": "\\textbackslash{}",
        "&": "\\&",
        "%": "\\%",
        "$": "\\$",
        "#": "\\#",
        "_": "\\_",
        "{": "\\{",
        "}": "\\}",
        "~": "\\textasciitilde{}",
        "^": "\\textasciicircum{}",
    }
    for k, v in repl.items():
        text = text.replace(k, v)
    return text


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
    source_theme = source.get("theme", {}) if isinstance(source.get("theme", {}), dict) else {}
    theme_node_fill = hex_or_default(source_theme.get("node_fill"), "#FFFFFF")
    theme_node_border = hex_or_default(source_theme.get("node_border"), "#1E293B")
    theme_node_text = hex_or_default(source_theme.get("node_text"), "#0F172A")

    nodes_raw = source.get("nodes", []) if isinstance(source.get("nodes", []), list) else []
    nodes_by_id: Dict[str, dict] = {str(n.get("id", "")): n for n in nodes_raw}
    node_color_by_id, _ = node_category_color_maps(nodes_raw, source.get("groups", []), source_theme)
    edges_by_id: Dict[str, dict] = {str(e.get("id", "")): e for e in source.get("edges", [])}

    lines: List[str] = []
    lines.append("\\documentclass[tikz,border=6pt]{standalone}")
    lines.append("\\usepackage{tikz}")
    lines.append("\\begin{document}")
    lines.append("\\begin{tikzpicture}[x=1pt,y=1pt,line cap=round,line join=round]")
    lines.append(f"\\path[use as bounding box] (0,0) rectangle ({width},{height});")

    for group in layout.get("groups", []):
        bbox = group.get("bbox_px")
        if not bbox or len(bbox) != 4:
            continue
        gx, gy, gw, gh = [int(v) for v in bbox]
        style = group.get("style", {}) if isinstance(group.get("style", {}), dict) else {}
        fill = hex_to_tikz_rgb(style.get("fill"), "#FFFFFF")
        stroke = hex_to_tikz_rgb(style.get("stroke"), "#94A3B8")
        label = escape_tex(str(group.get("label", "")))

        y_top = height - gy
        y_bottom = height - (gy + gh)
        lines.append(
            f"\\draw[rounded corners=18pt, fill={fill}, fill opacity=0.18, draw={stroke}, line width=1.5pt] "
            f"({gx},{y_bottom}) rectangle ({gx + gw},{y_top});"
        )
        if label:
            lines.append(
                f"\\node[anchor=west, text={stroke}, font=\\small] at ({gx + 10},{y_top - 16}) {{{label}}};"
            )

    for edge in layout.get("edges", []):
        edge_id = str(edge.get("id", ""))
        src_edge = edges_by_id.get(edge_id, {})
        style = edge.get("style", {}) if isinstance(edge.get("style", {}), dict) else {}
        color = hex_to_tikz_rgb(style.get("color"), "#475569")
        width_px = int(style.get("width", 3))
        pattern = str(style.get("pattern", "solid"))
        direction = str(style.get("direction", "single"))
        route_points = edge.get("polyline_px", [])
        if not isinstance(route_points, list) or len(route_points) < 2:
            continue

        points: List[Point] = []
        for p in route_points:
            if isinstance(p, list) and len(p) == 2:
                points.append((int(p[0]), int(p[1])))
        if len(points) < 2:
            continue

        dash_opt = ""
        if pattern == "dashed":
            dash_opt = ",dash pattern=on 7pt off 4pt"
        elif pattern == "dotted":
            dash_opt = ",dotted"

        arrow_opt = "->"
        if direction == "both":
            arrow_opt = "<->"
        elif direction == "none":
            arrow_opt = "-"

        path = points_to_tikz_path(points, scale_y=height)
        lines.append(
            f"\\draw[{arrow_opt}, draw={color}, line width={width_px/1.5:.2f}pt{dash_opt}] {path};"
        )

        label = escape_tex(str(src_edge.get("label", edge.get("label", ""))))
        lb = edge.get("label_bbox_px")
        if label and isinstance(lb, list) and len(lb) == 4:
            lx, ly, lw, lh = [int(v) for v in lb]
            cx = lx + lw // 2
            cy = ly + lh // 2
            lines.append(
                f"\\node[draw=gray!40, fill=white, rounded corners=2pt, inner sep=2pt, font=\\scriptsize] "
                f"at ({cx},{height - cy}) {{{label}}};"
            )

    for node in layout.get("nodes", []):
        node_id = str(node.get("id", ""))
        src_node = nodes_by_id.get(node_id, {})
        style = src_node.get("style", {}) if isinstance(src_node.get("style", {}), dict) else {}
        category_fill = node_color_by_id.get(node_id)
        fill_hex = hex_or_default(style.get("fill") or category_fill, theme_node_fill)
        stroke_hex = hex_or_default(style.get("stroke"), theme_node_border)
        text_hex = hex_or_default(
            style.get("text"),
            contrast_text(fill_hex) if category_fill and not style.get("text") else theme_node_text,
        )
        fill = hex_to_tikz_rgb(fill_hex, "#FFFFFF")
        stroke = hex_to_tikz_rgb(stroke_hex, "#1E293B")
        text_color = hex_to_tikz_rgb(text_hex, "#0F172A")
        shape = str(node.get("shape", "rounded")).lower()
        label = escape_tex(str(src_node.get("label", node.get("label", ""))))

        bbox = node.get("bbox_px")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        x, y, w, h = [int(v) for v in bbox]
        y_top = height - y
        y_bottom = height - (y + h)
        cx = x + w // 2
        cy = y + h // 2

        if shape == "ellipse":
            lines.append(
                f"\\draw[draw={stroke}, fill={fill}, line width=1.6pt] ({cx},{height - cy}) ellipse ({w/2:.1f}pt and {h/2:.1f}pt);"
            )
        else:
            radius = h / 2 if shape == "pill" else 12
            lines.append(
                f"\\draw[rounded corners={radius:.1f}pt, draw={stroke}, fill={fill}, line width=1.6pt] "
                f"({x},{y_bottom}) rectangle ({x + w},{y_top});"
            )

        if label:
            lines.append(
                f"\\node[text={text_color}, align=center, font=\\small] at ({cx},{height - cy}) {{{label}}};"
            )

    lines.append("\\end{tikzpicture}")
    lines.append("\\end{document}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")

    print(f"[render_tikz] source={source_path}")
    print(f"[render_tikz] layout={layout_path}")
    print(f"[render_tikz] output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
