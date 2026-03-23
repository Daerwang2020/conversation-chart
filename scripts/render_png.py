
"""Render conversation chart DSL JSON to PNG and layout JSON.

Features:
- Rounded / ellipse / pill nodes
- Group containers
- Relation-aware edge styles
- Straight / orthogonal / curve routing
- Automatic orthogonal obstacle-avoid routing
- Occlusion-aware edge label placement
- Occlusion report in layout output
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont


Color = Tuple[int, int, int, int]
Point = Tuple[int, int]
Rect = Tuple[int, int, int, int]
Segment = Tuple[Point, Point]


RELATION_PRESETS: Dict[str, dict] = {
    "sync_request": {"color": "#2563EB", "pattern": "solid", "direction": "single", "width": 3},
    "async_event": {"color": "#7C3AED", "pattern": "dashed", "direction": "single", "width": 3},
    "stream": {"color": "#0891B2", "pattern": "solid", "direction": "single", "width": 4},
    "dependency": {"color": "#64748B", "pattern": "dotted", "direction": "single", "width": 2},
    "replication": {"color": "#0F766E", "pattern": "solid", "direction": "both", "width": 3},
    "feedback": {"color": "#EA580C", "pattern": "dashed", "direction": "single", "width": 3},
    "observability": {"color": "#9333EA", "pattern": "dotted", "direction": "single", "width": 2},
    "control": {"color": "#DC2626", "pattern": "solid", "direction": "single", "width": 3},
}

@dataclass
class Node:
    id: str
    label: str
    x: int
    y: int
    width: int
    height: int
    source_ref: str
    style: dict = field(default_factory=dict)
    shape: str = "rounded"
    category: str = ""

    @property
    def center(self) -> Point:
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def rect(self) -> Rect:
        return (self.x, self.y, self.x + self.width, self.y + self.height)


@dataclass
class Edge:
    id: str
    from_id: str
    to_id: str
    label: str
    source_ref: str
    style: dict = field(default_factory=dict)
    relation: str = ""
    waypoints: List[Point] = field(default_factory=list)


@dataclass
class Group:
    id: str
    label: str
    node_ids: List[str]
    style: dict


@dataclass
class RoutedEdge:
    edge: Edge
    points: List[Point]
    style: dict


def parse_color(value: str | None, default: Color) -> Color:
    if not value:
        return default
    text = value.strip().lstrip("#")
    try:
        if len(text) == 6:
            return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), 255)
        if len(text) == 8:
            return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), int(text[6:8], 16))
    except ValueError:
        return default
    return default


def normalize_hex(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if not text.startswith("#"):
        return None
    text = text.upper()
    if len(text) == 7:
        return text
    if len(text) == 9:
        return text[:7]
    return None


def contrast_text_hex(fill_hex: str) -> str:
    text = normalize_hex(fill_hex)
    if not text:
        return "#0F172A"
    r = int(text[1:3], 16)
    g = int(text[3:5], 16)
    b = int(text[5:7], 16)
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#0F172A" if luma >= 145 else "#F8FAFC"


def parse_node_cycle(raw: object) -> List[str]:
    cycle: List[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                normalized = normalize_hex(item)
                if normalized:
                    cycle.append(normalized)
    return cycle


def normalized_key(text: str) -> str:
    return text.strip().lower().replace(" ", "_")


def parse_category_colors(raw: object) -> Dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    result: Dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        color = normalize_hex(value)
        cat = normalized_key(key)
        if color and cat:
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


def build_group_map(groups: List[Group]) -> Dict[str, str]:
    node_to_group: Dict[str, str] = {}
    for group in groups:
        key = normalized_key(group.id) or normalized_key(group.label)
        if not key:
            continue
        for node_id in group.node_ids:
            if node_id not in node_to_group:
                node_to_group[node_id] = key
    return node_to_group


def resolve_node_category(
    node: Node,
    source: str,
    group_key: str | None,
    assignments: Dict[str, str],
) -> str | None:
    if node.id in assignments:
        return assignments[node.id]

    source = normalized_key(source or "auto")
    node_category = normalized_key(node.category)

    if source == "node":
        return node_category or normalized_key(node.id)
    if source == "group":
        return group_key
    if source == "none":
        return None

    # auto: node.category first, group fallback
    if node_category:
        return node_category
    if group_key:
        return group_key
    return None


def category_color_map(
    nodes: List[Node],
    groups: List[Group],
    theme: dict,
) -> Tuple[Dict[str, str], Dict[str, str]]:
    color_mode = normalized_key(str(theme.get("color_mode", "category")))
    category_source = str(theme.get("category_source", "auto"))
    cycle = theme.get("node_cycle", []) or []
    category_colors = theme.get("category_colors", {}) or {}
    assignments = theme.get("category_assignments", {}) or {}
    group_map = build_group_map(groups)

    node_category: Dict[str, str] = {}
    category_to_color: Dict[str, str] = dict(category_colors)
    next_idx = 0

    for node in nodes:
        if color_mode == "node":
            key = normalized_key(node.id)
        else:
            key = resolve_node_category(
                node=node,
                source=category_source,
                group_key=group_map.get(node.id),
                assignments=assignments,
            )
        if not key:
            continue
        if key not in category_to_color and cycle:
            category_to_color[key] = cycle[next_idx % len(cycle)]
            next_idx += 1
        if key in category_to_color:
            node_category[node.id] = key
    node_colors = {nid: category_to_color[key] for nid, key in node_category.items() if key in category_to_color}
    return (node_colors, node_category)


def normalize_color(c: Color) -> Tuple[int, int, int]:
    return (c[0], c[1], c[2])


def require_unique_ids(items: List[dict], key: str, kind: str) -> None:
    seen: set[str] = set()
    for obj in items:
        item_id = str(obj.get(key, "")).strip()
        if not item_id:
            raise ValueError(f"{kind} missing required key '{key}'")
        if item_id in seen:
            raise ValueError(f"Duplicate {kind} id: {item_id}")
        seen.add(item_id)


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
    ]
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def measure_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    if not text:
        return (0, 0)
    bbox = draw.textbbox((0, 0), text, font=font)
    return (bbox[2] - bbox[0], bbox[3] - bbox[1])


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    text = text.strip()
    if not text:
        return []

    words = text.split()
    if len(words) == 1:
        lines: List[str] = []
        current = ""
        for ch in words[0]:
            probe = current + ch
            if current and measure_text(draw, probe, font)[0] > max_width:
                lines.append(current)
                current = ch
            else:
                current = probe
        if current:
            lines.append(current)
        return lines

    lines: List[str] = []
    current = ""
    for word in words:
        probe = word if not current else f"{current} {word}"
        if current and measure_text(draw, probe, font)[0] > max_width:
            lines.append(current)
            current = word
        else:
            current = probe
    if current:
        lines.append(current)
    return lines


def point_in_rect(point: Point, rect: Rect) -> bool:
    x, y = point
    x1, y1, x2, y2 = rect
    return x1 <= x <= x2 and y1 <= y <= y2


def rect_overlap_area(a: Rect, b: Rect) -> int:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0
    return int((ix2 - ix1) * (iy2 - iy1))


def ccw(a: Point, b: Point, c: Point) -> bool:
    return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])


def segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    return ccw(a, c, d) != ccw(b, c, d) and ccw(a, b, c) != ccw(a, b, d)


def segment_intersects_rect(segment: Segment, rect: Rect) -> bool:
    p1, p2 = segment
    if point_in_rect(p1, rect) or point_in_rect(p2, rect):
        return True
    x1, y1, x2, y2 = rect
    edges = [
        ((x1, y1), (x2, y1)),
        ((x2, y1), (x2, y2)),
        ((x2, y2), (x1, y2)),
        ((x1, y2), (x1, y1)),
    ]
    return any(segments_intersect(p1, p2, e1, e2) for e1, e2 in edges)


def polyline_segments(points: List[Point]) -> List[Segment]:
    if len(points) < 2:
        return []
    return list(zip(points[:-1], points[1:]))


def inflate_rect(rect: Rect, pad: int, width: int, height: int) -> Rect:
    x1, y1, x2, y2 = rect
    return (
        max(0, x1 - pad),
        max(0, y1 - pad),
        min(width, x2 + pad),
        min(height, y2 + pad),
    )


def simplify_polyline(points: List[Point]) -> List[Point]:
    if len(points) <= 2:
        return points
    simplified = [points[0]]
    for i in range(1, len(points) - 1):
        a = simplified[-1]
        b = points[i]
        c = points[i + 1]
        if (a[0] == b[0] == c[0]) or (a[1] == b[1] == c[1]):
            continue
        simplified.append(b)
    simplified.append(points[-1])

    deduped: List[Point] = []
    for p in simplified:
        if not deduped or deduped[-1] != p:
            deduped.append(p)
    return deduped


def nearest_free_cell(target: Tuple[int, int], blocked: set[Tuple[int, int]], cols: int, rows: int) -> Tuple[int, int] | None:
    tx, ty = target
    if 0 <= tx < cols and 0 <= ty < rows and (tx, ty) not in blocked:
        return (tx, ty)

    max_radius = max(cols, rows)
    for r in range(1, max_radius):
        for dx in range(-r, r + 1):
            for dy in (-r, r):
                x = tx + dx
                y = ty + dy
                if 0 <= x < cols and 0 <= y < rows and (x, y) not in blocked:
                    return (x, y)
        for dy in range(-r + 1, r):
            for dx in (-r, r):
                x = tx + dx
                y = ty + dy
                if 0 <= x < cols and 0 <= y < rows and (x, y) not in blocked:
                    return (x, y)
    return None


def astar_route(
    start: Tuple[int, int],
    goal: Tuple[int, int],
    blocked: set[Tuple[int, int]],
    cols: int,
    rows: int,
    max_expansions: int,
) -> List[Tuple[int, int]] | None:
    def heuristic(a: Tuple[int, int], b: Tuple[int, int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    open_heap: List[Tuple[int, int, Tuple[int, int]]] = []
    heapq.heappush(open_heap, (heuristic(start, goal), 0, start))
    came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
    gscore: Dict[Tuple[int, int], int] = {start: 0}
    visited: set[Tuple[int, int]] = set()

    expansions = 0
    while open_heap:
        _, g, current = heapq.heappop(open_heap)
        if current in visited:
            continue
        visited.add(current)
        expansions += 1
        if expansions > max_expansions:
            return None

        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path

        cx, cy = current
        for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
            if nx < 0 or ny < 0 or nx >= cols or ny >= rows:
                continue
            neighbor = (nx, ny)
            if neighbor in blocked:
                continue
            tentative = g + 1
            if tentative < gscore.get(neighbor, 10**9):
                came_from[neighbor] = current
                gscore[neighbor] = tentative
                f = tentative + heuristic(neighbor, goal)
                heapq.heappush(open_heap, (f, tentative, neighbor))

    return None


def orthogonal_obstacle_route(
    start: Point,
    end: Point,
    nodes: Dict[str, Node],
    from_id: str,
    to_id: str,
    canvas_w: int,
    canvas_h: int,
    grid_step: int,
    obstacle_padding: int,
    max_expansions: int,
) -> List[Point] | None:
    step = max(8, grid_step)
    cols = canvas_w // step + 1
    rows = canvas_h // step + 1

    blocked: set[Tuple[int, int]] = set()
    for node_id, node in nodes.items():
        if node_id in {from_id, to_id}:
            continue
        x1, y1, x2, y2 = inflate_rect(node.rect, obstacle_padding, canvas_w, canvas_h)
        cx1 = max(0, x1 // step)
        cy1 = max(0, y1 // step)
        cx2 = min(cols - 1, x2 // step)
        cy2 = min(rows - 1, y2 // step)
        for cx in range(cx1, cx2 + 1):
            for cy in range(cy1, cy2 + 1):
                blocked.add((cx, cy))

    border = max(1, obstacle_padding // max(8, step // 2))
    for cx in range(cols):
        for cy in range(rows):
            if cx < border or cy < border or cx >= cols - border or cy >= rows - border:
                blocked.add((cx, cy))

    s_cell = (int(round(start[0] / step)), int(round(start[1] / step)))
    e_cell = (int(round(end[0] / step)), int(round(end[1] / step)))

    for anchor in (s_cell, e_cell):
        ax, ay = anchor
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                nx, ny = ax + dx, ay + dy
                if 0 <= nx < cols and 0 <= ny < rows:
                    blocked.discard((nx, ny))

    s_free = nearest_free_cell(s_cell, blocked, cols, rows)
    e_free = nearest_free_cell(e_cell, blocked, cols, rows)
    if s_free is None or e_free is None:
        return None

    path_cells = astar_route(s_free, e_free, blocked, cols, rows, max_expansions=max_expansions)
    if not path_cells:
        return None

    path_points = [(cx * step, cy * step) for cx, cy in path_cells]
    polyline = [start]
    if path_points and path_points[0] != start:
        polyline.append(path_points[0])
    polyline.extend(path_points[1:])
    if not polyline or polyline[-1] != end:
        polyline.append(end)
    return simplify_polyline(polyline)


def interpolate(p1: Point, p2: Point, t: float) -> Point:
    return (int(round(p1[0] + (p2[0] - p1[0]) * t)), int(round(p1[1] + (p2[1] - p1[1]) * t)))


def point_on_polyline(points: List[Point], frac: float) -> Point:
    if not points:
        return (0, 0)
    if len(points) == 1:
        return points[0]

    frac = min(1.0, max(0.0, frac))
    lengths = [math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1]) for i in range(len(points) - 1)]
    total = sum(lengths)
    if total <= 0:
        return points[len(points) // 2]
    target = total * frac
    walked = 0.0
    for i, seg in enumerate(lengths):
        if walked + seg >= target:
            local_t = (target - walked) / max(1e-6, seg)
            return interpolate(points[i], points[i + 1], local_t)
        walked += seg
    return points[-1]


def draw_dashed_segment(draw: ImageDraw.ImageDraw, p1: Point, p2: Point, color: Tuple[int, int, int], width: int, dash: int, gap: int) -> None:
    length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    if length < 1:
        return
    traveled = 0.0
    while traveled < length:
        start_t = traveled / length
        end_t = min((traveled + dash) / length, 1.0)
        a = interpolate(p1, p2, start_t)
        b = interpolate(p1, p2, end_t)
        draw.line([a, b], fill=color, width=width)
        traveled += dash + gap


def draw_dotted_segment(draw: ImageDraw.ImageDraw, p1: Point, p2: Point, color: Tuple[int, int, int], radius: int, spacing: int) -> None:
    length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    if length < 1:
        return
    steps = max(1, int(length // spacing))
    for i in range(steps + 1):
        t = i / steps
        x, y = interpolate(p1, p2, t)
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=color)


def draw_polyline(draw: ImageDraw.ImageDraw, points: List[Point], color: Tuple[int, int, int], width: int, pattern: str) -> None:
    if len(points) < 2:
        return
    for i in range(len(points) - 1):
        a = points[i]
        b = points[i + 1]
        if pattern == "dashed":
            draw_dashed_segment(draw, a, b, color, width, dash=14, gap=10)
        elif pattern == "dotted":
            draw_dotted_segment(draw, a, b, color, radius=max(1, width), spacing=12)
        else:
            draw.line([a, b], fill=color, width=width)


def draw_arrowhead(draw: ImageDraw.ImageDraw, from_pt: Point, to_pt: Point, color: Tuple[int, int, int], width: int) -> None:
    dx = to_pt[0] - from_pt[0]
    dy = to_pt[1] - from_pt[1]
    length = max(1.0, math.hypot(dx, dy))
    ux = dx / length
    uy = dy / length
    size = max(8.0, width * 3.5)

    left = (
        int(round(to_pt[0] - ux * size - uy * (size * 0.45))),
        int(round(to_pt[1] - uy * size + ux * (size * 0.45))),
    )
    right = (
        int(round(to_pt[0] - ux * size + uy * (size * 0.45))),
        int(round(to_pt[1] - uy * size - ux * (size * 0.45))),
    )
    draw.line([to_pt, left], fill=color, width=width)
    draw.line([to_pt, right], fill=color, width=width)


def draw_node_shape(draw: ImageDraw.ImageDraw, node: Node, fill: Color, stroke: Color, radius: int, border_width: int) -> None:
    x1, y1, x2, y2 = node.rect
    shape = node.shape.lower()
    if shape == "ellipse":
        draw.ellipse([x1, y1, x2, y2], fill=fill, outline=stroke, width=border_width)
    elif shape == "pill":
        draw.rounded_rectangle([x1, y1, x2, y2], radius=max(radius, node.height // 2), fill=fill, outline=stroke, width=border_width)
    else:
        draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill, outline=stroke, width=border_width)


def compute_text_lines(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, box_w: int) -> List[str]:
    return wrap_text(draw, text, font, max_width=max(20, box_w - 24))[:4]


def draw_text_centered(draw: ImageDraw.ImageDraw, box: Rect, text: str, color: Tuple[int, int, int], font: ImageFont.ImageFont) -> Rect | None:
    x1, y1, x2, y2 = box
    w = x2 - x1
    h = y2 - y1
    lines = compute_text_lines(draw, text, font, w)
    if not lines:
        return None

    line_h = max(12, measure_text(draw, "Ag", font)[1] + 2)
    total_h = line_h * len(lines)
    cy = y1 + max(0, (h - total_h) // 2)

    min_x = 10**9
    min_y = 10**9
    max_x = -10**9
    max_y = -10**9
    for line in lines:
        tw, th = measure_text(draw, line, font)
        cx = x1 + max(0, (w - tw) // 2)
        draw.text((cx, cy), line, fill=color, font=font)
        min_x = min(min_x, cx)
        min_y = min(min_y, cy)
        max_x = max(max_x, cx + tw)
        max_y = max(max_y, cy + th)
        cy += line_h
    return (min_x, min_y, max_x, max_y)


def estimate_text_bbox(draw: ImageDraw.ImageDraw, box: Rect, text: str, font: ImageFont.ImageFont) -> Rect | None:
    x1, y1, x2, y2 = box
    w = x2 - x1
    h = y2 - y1
    lines = compute_text_lines(draw, text, font, w)
    if not lines:
        return None

    line_h = max(12, measure_text(draw, "Ag", font)[1] + 2)
    total_h = line_h * len(lines)
    cy = y1 + max(0, (h - total_h) // 2)

    min_x = 10**9
    min_y = 10**9
    max_x = -10**9
    max_y = -10**9
    for line in lines:
        tw, th = measure_text(draw, line, font)
        cx = x1 + max(0, (w - tw) // 2)
        min_x = min(min_x, cx)
        min_y = min(min_y, cy)
        max_x = max(max_x, cx + tw)
        max_y = max(max_y, cy + th)
        cy += line_h
    return (min_x, min_y, max_x, max_y)


def theme_defaults(dsl: dict, args: argparse.Namespace) -> dict:
    raw = dsl.get("theme", {}) if isinstance(dsl.get("theme", {}), dict) else {}
    node_cycle = parse_node_cycle(raw.get("node_cycle"))
    category_colors = parse_category_colors(raw.get("category_colors"))
    category_assignments = parse_category_assignments(raw.get("category_assignments"))
    return {
        "background": raw.get("background", raw.get("canvas_bg", args.background)),
        "node_fill": raw.get("node_fill", args.node_fill),
        "node_border": raw.get("node_border", args.node_border),
        "node_text": raw.get("node_text", args.node_text),
        "edge_color": raw.get("edge_color", args.edge_color),
        "group_fill": raw.get("group_fill", "#FFFFFFAA"),
        "group_stroke": raw.get("group_stroke", "#94A3B8"),
        "group_text": raw.get("group_text", "#475569"),
        "color_mode": str(raw.get("color_mode", "category")),
        "category_source": str(raw.get("category_source", "auto")),
        "node_cycle": node_cycle,
        "category_colors": category_colors,
        "category_assignments": category_assignments,
    }


def edge_style(edge: Edge, default_edge: Color, default_width: int) -> dict:
    merged: dict = {}
    merged.update(RELATION_PRESETS.get(edge.relation, {}))
    merged.update(edge.style)

    color = parse_color(merged.get("color"), default_edge)
    width = int(max(1, merged.get("width", default_width)))
    pattern = str(merged.get("pattern", "solid")).lower()
    if pattern not in {"solid", "dashed", "dotted"}:
        pattern = "solid"
    route = str(merged.get("route", "straight")).lower()
    if route not in {"straight", "orthogonal", "curve"}:
        route = "straight"
    direction = str(merged.get("direction", "single")).lower()
    if direction not in {"single", "both", "none"}:
        direction = "single"

    return {
        "color": color,
        "width": width,
        "pattern": pattern,
        "route": route,
        "direction": direction,
        "curve_offset": int(merged.get("curve_offset", 70)),
        "avoid_obstacles": bool(merged.get("avoid_obstacles", True)),
    }


def orthogonal_points(start: Point, end: Point, direction: str) -> List[Point]:
    x1, y1 = start
    x2, y2 = end
    if direction == "TB":
        mid_y = (y1 + y2) // 2
        return [start, (x1, mid_y), (x2, mid_y), end]
    mid_x = (x1 + x2) // 2
    return [start, (mid_x, y1), (mid_x, y2), end]


def curve_points(start: Point, end: Point, offset: int) -> List[Point]:
    x1, y1 = start
    x2, y2 = end
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2 - offset
    pts: List[Point] = []
    for i in range(31):
        t = i / 30.0
        x = int(round((1 - t) * (1 - t) * x1 + 2 * (1 - t) * t * cx + t * t * x2))
        y = int(round((1 - t) * (1 - t) * y1 + 2 * (1 - t) * t * cy + t * t * y2))
        pts.append((x, y))
    return pts


def edge_endpoints(src: Node, dst: Node, direction: str) -> Tuple[Point, Point]:
    sx, sy = src.center
    dx, dy = dst.center
    if direction == "TB":
        if dy >= sy:
            return (sx, src.y + src.height), (dx, dst.y)
        return (sx, src.y), (dx, dst.y + dst.height)
    if dx >= sx:
        return (src.x + src.width, sy), (dst.x, dy)
    return (src.x, sy), (dst.x + dst.width, dy)


def parse_points(raw: object) -> List[Point]:
    if not isinstance(raw, list):
        return []
    points: List[Point] = []
    for item in raw:
        if isinstance(item, list) and len(item) == 2:
            try:
                points.append((int(item[0]), int(item[1])))
            except (ValueError, TypeError):
                continue
    return points


def build_nodes(dsl: dict, direction: str, padding: int, columns: int) -> List[Node]:
    raw_nodes = dsl.get("nodes", [])
    if not isinstance(raw_nodes, list):
        raise ValueError("'nodes' must be a list")
    require_unique_ids(raw_nodes, "id", "node")

    default_w = 200
    default_h = 100
    gap_x = 90
    gap_y = 90
    columns = max(1, columns)

    nodes: List[Node] = []
    for idx, raw in enumerate(raw_nodes):
        width = int(max(80, raw.get("width", default_w)))
        height = int(max(40, raw.get("height", default_h)))
        x_raw = raw.get("x")
        y_raw = raw.get("y")
        if x_raw is None or y_raw is None:
            row = idx // columns
            col = idx % columns
            x = padding + col * (default_w + gap_x)
            y = padding + row * (default_h + gap_y)
            if direction == "TB":
                x, y = y, x
        else:
            x = int(x_raw)
            y = int(y_raw)

        nodes.append(
            Node(
                id=str(raw["id"]),
                label=str(raw.get("label", "")),
                x=x,
                y=y,
                width=width,
                height=height,
                source_ref=f"nodes[{idx}]",
                style=raw.get("style", {}) if isinstance(raw.get("style", {}), dict) else {},
                shape=str(raw.get("shape", "rounded")),
                category=str(raw.get("category", "")).strip(),
            )
        )
    return nodes


def build_edges(dsl: dict, nodes_by_id: Dict[str, Node]) -> List[Edge]:
    raw_edges = dsl.get("edges", [])
    if not isinstance(raw_edges, list):
        raise ValueError("'edges' must be a list")
    require_unique_ids(raw_edges, "id", "edge")

    edges: List[Edge] = []
    for idx, raw in enumerate(raw_edges):
        edge_id = str(raw["id"])
        from_id = str(raw.get("from", ""))
        to_id = str(raw.get("to", ""))
        if from_id not in nodes_by_id:
            raise ValueError(f"Edge {edge_id} references missing node: {from_id}")
        if to_id not in nodes_by_id:
            raise ValueError(f"Edge {edge_id} references missing node: {to_id}")
        edges.append(
            Edge(
                id=edge_id,
                from_id=from_id,
                to_id=to_id,
                label=str(raw.get("label", "")),
                source_ref=f"edges[{idx}]",
                style=raw.get("style", {}) if isinstance(raw.get("style", {}), dict) else {},
                relation=str(raw.get("relation", "")).strip(),
                waypoints=parse_points(raw.get("waypoints", [])),
            )
        )
    return edges


def build_groups(dsl: dict) -> List[Group]:
    raw_groups = dsl.get("groups", [])
    if not isinstance(raw_groups, list):
        return []
    groups: List[Group] = []
    for idx, raw in enumerate(raw_groups):
        if not isinstance(raw, dict):
            continue
        groups.append(
            Group(
                id=str(raw.get("id", f"group_{idx}")),
                label=str(raw.get("label", "")),
                node_ids=[str(v) for v in raw.get("nodes", []) if isinstance(v, str)],
                style=raw.get("style", {}) if isinstance(raw.get("style", {}), dict) else {},
            )
        )
    return groups


def choose_label_rect(
    edge_id: str,
    points: List[Point],
    label_w: int,
    label_h: int,
    canvas_rect: Rect,
    node_rects: List[Rect],
    node_text_rects: List[Rect],
    group_label_rects: List[Rect],
    placed_label_rects: List[Rect],
    all_segments: Dict[str, List[Segment]],
) -> Tuple[Rect, float, int]:
    offsets = [
        (0, -26),
        (0, 26),
        (24, 0),
        (-24, 0),
        (24, -20),
        (-24, -20),
        (24, 20),
        (-24, 20),
        (0, -40),
        (0, 40),
    ]
    fracs = [0.38, 0.5, 0.62]

    best_rect: Rect | None = None
    best_penalty = float("inf")
    best_conflicts = 0
    cx1, cy1, cx2, cy2 = canvas_rect

    for frac in fracs:
        bx, by = point_on_polyline(points, frac)
        for ox, oy in offsets:
            rx1 = int(bx + ox - label_w // 2)
            ry1 = int(by + oy - label_h // 2)
            rx2 = rx1 + label_w
            ry2 = ry1 + label_h
            rect = (rx1, ry1, rx2, ry2)

            penalty = 0.0
            conflicts = 0
            if rx1 < cx1 or ry1 < cy1 or rx2 > cx2 or ry2 > cy2:
                penalty += 5000.0
                conflicts += 1

            for r in node_rects:
                area = rect_overlap_area(rect, r)
                if area:
                    penalty += area * 8.0
                    conflicts += 1
            for r in node_text_rects:
                area = rect_overlap_area(rect, r)
                if area:
                    penalty += area * 16.0
                    conflicts += 1
            for r in group_label_rects:
                area = rect_overlap_area(rect, r)
                if area:
                    penalty += area * 12.0
                    conflicts += 1
            for r in placed_label_rects:
                area = rect_overlap_area(rect, r)
                if area:
                    penalty += area * 14.0
                    conflicts += 1

            for seg_owner, segments in all_segments.items():
                for seg in segments:
                    if segment_intersects_rect(seg, rect):
                        if seg_owner == edge_id:
                            penalty += 60.0
                        else:
                            penalty += 130.0
                            conflicts += 1

            if penalty < best_penalty:
                best_penalty = penalty
                best_rect = rect
                best_conflicts = conflicts

    if best_rect is None:
        bx, by = point_on_polyline(points, 0.5)
        best_rect = (bx - label_w // 2, by - label_h // 2, bx + label_w // 2, by + label_h // 2)
        best_penalty = 999999.0
        best_conflicts = 1
    return best_rect, best_penalty, best_conflicts


def detect_occlusions(
    routed_edges: List[RoutedEdge],
    node_text_boxes: Dict[str, Rect],
    edge_label_boxes: Dict[str, Rect],
    threshold: int,
) -> dict:
    issues: List[dict] = []
    for routed in routed_edges:
        e = routed.edge
        for seg in polyline_segments(routed.points):
            for node_id, rect in node_text_boxes.items():
                if node_id in {e.from_id, e.to_id}:
                    continue
                if segment_intersects_rect(seg, rect):
                    issues.append({"type": "edge_vs_node_text", "edge_id": e.id, "node_id": node_id})

    ids = sorted(edge_label_boxes.keys())
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if rect_overlap_area(edge_label_boxes[ids[i]], edge_label_boxes[ids[j]]) > 0:
                issues.append({"type": "edge_label_vs_edge_label", "edge_a": ids[i], "edge_b": ids[j]})

    return {
        "total_issues": len(issues),
        "status": "ok" if len(issues) <= threshold else "warning",
        "issues": issues[:200],
    }


def edge_text_crossings(points: List[Point], from_id: str, to_id: str, node_text_boxes: Dict[str, Rect]) -> int:
    count = 0
    for seg in polyline_segments(points):
        for node_id, rect in node_text_boxes.items():
            if node_id in {from_id, to_id}:
                continue
            if segment_intersects_rect(seg, rect):
                count += 1
    return count


def render(dsl: dict, args: argparse.Namespace) -> dict:
    direction = str(dsl.get("direction", "LR")).upper()
    if direction not in {"LR", "TB"}:
        direction = "LR"

    theme = theme_defaults(dsl, args)
    nodes = build_nodes(dsl, direction=direction, padding=args.padding, columns=args.columns)
    nodes_by_id = {n.id: n for n in nodes}
    edges = build_edges(dsl, nodes_by_id)
    groups = build_groups(dsl)

    max_right = max((n.x + n.width for n in nodes), default=420)
    max_bottom = max((n.y + n.height for n in nodes), default=280)
    width = max(500, max_right + args.padding)
    height = max(320, max_bottom + args.padding)

    bg = parse_color(theme["background"], (246, 248, 252, 255))
    default_node_fill = parse_color(theme["node_fill"], (255, 255, 255, 255))
    default_node_border = parse_color(theme["node_border"], (30, 41, 59, 255))
    default_node_text = parse_color(theme["node_text"], (15, 23, 42, 255))
    default_edge = parse_color(theme["edge_color"], (71, 85, 105, 255))
    default_group_fill = parse_color(theme["group_fill"], (255, 255, 255, 120))
    default_group_stroke = parse_color(theme["group_stroke"], (148, 163, 184, 200))
    default_group_text = parse_color(theme["group_text"], (71, 85, 105, 255))

    img = Image.new("RGBA", (width, height), bg)
    draw = ImageDraw.Draw(img, "RGBA")
    font = load_font(args.font_size)
    group_font = load_font(max(11, args.font_size - 3))
    edge_font = load_font(max(10, args.font_size - 5))

    node_rects = [n.rect for n in nodes]
    node_text_rects: Dict[str, Rect] = {}
    group_label_rects: List[Rect] = []

    group_layout: List[dict] = []
    for group in groups:
        group_nodes = [nodes_by_id[nid] for nid in group.node_ids if nid in nodes_by_id]
        if not group_nodes:
            continue

        pad = int(max(8, group.style.get("padding", 24)))
        gx1 = min(n.x for n in group_nodes) - pad
        gy1 = min(n.y for n in group_nodes) - pad - 24
        gx2 = max(n.x + n.width for n in group_nodes) + pad
        gy2 = max(n.y + n.height for n in group_nodes) + pad

        fill = parse_color(group.style.get("fill"), default_group_fill)
        stroke = parse_color(group.style.get("stroke"), default_group_stroke)
        text = parse_color(group.style.get("text"), default_group_text)
        radius = int(max(6, group.style.get("radius", 18)))

        draw.rounded_rectangle([gx1, gy1, gx2, gy2], radius=radius, fill=fill, outline=stroke, width=2)
        label_rect = None
        if group.label:
            draw.text((gx1 + 10, gy1 + 8), group.label, fill=normalize_color(text), font=group_font)
            tw, th = measure_text(draw, group.label, group_font)
            label_rect = (gx1 + 10, gy1 + 8, gx1 + 10 + tw, gy1 + 8 + th)
            group_label_rects.append(label_rect)

        group_layout.append(
            {
                "id": group.id,
                "label": group.label,
                "nodes": group.node_ids,
                "bbox_px": [gx1, gy1, gx2 - gx1, gy2 - gy1],
                "label_bbox_px": [label_rect[0], label_rect[1], label_rect[2] - label_rect[0], label_rect[3] - label_rect[1]]
                if label_rect
                else None,
                "style": group.style,
            }
        )

    routed_edges: List[RoutedEdge] = []
    for edge in edges:
        src = nodes_by_id[edge.from_id]
        dst = nodes_by_id[edge.to_id]
        start, end = edge_endpoints(src, dst, direction)
        style = edge_style(edge, default_edge=default_edge, default_width=args.edge_width)

        if edge.waypoints:
            points = [start, *edge.waypoints, end]
        elif style["route"] == "orthogonal":
            points = None
            if args.orth_avoid and style["avoid_obstacles"]:
                points = orthogonal_obstacle_route(
                    start=start,
                    end=end,
                    nodes=nodes_by_id,
                    from_id=edge.from_id,
                    to_id=edge.to_id,
                    canvas_w=width,
                    canvas_h=height,
                    grid_step=args.orth_step,
                    obstacle_padding=args.orth_padding,
                    max_expansions=args.orth_max_expansions,
                )
            if not points:
                points = orthogonal_points(start, end, direction)
        elif style["route"] == "curve":
            points = curve_points(start, end, style["curve_offset"])
        else:
            points = [start, end]
        routed_edges.append(RoutedEdge(edge=edge, points=simplify_polyline(points), style=style))

    if args.auto_fix_text_occlusion:
        estimated_text_boxes: Dict[str, Rect] = {}
        for node in nodes:
            box = estimate_text_bbox(draw, node.rect, node.label, font)
            if box:
                estimated_text_boxes[node.id] = box

        for routed in routed_edges:
            crossings = edge_text_crossings(
                points=routed.points,
                from_id=routed.edge.from_id,
                to_id=routed.edge.to_id,
                node_text_boxes=estimated_text_boxes,
            )
            if crossings <= 0:
                continue

            # Keep explicit manual waypoints stable.
            if routed.edge.waypoints:
                continue

            rerouted = orthogonal_obstacle_route(
                start=routed.points[0],
                end=routed.points[-1],
                nodes=nodes_by_id,
                from_id=routed.edge.from_id,
                to_id=routed.edge.to_id,
                canvas_w=width,
                canvas_h=height,
                grid_step=args.orth_step,
                obstacle_padding=args.orth_padding,
                max_expansions=args.orth_max_expansions,
            )
            if not rerouted:
                continue

            old_count = crossings
            new_count = edge_text_crossings(
                points=rerouted,
                from_id=routed.edge.from_id,
                to_id=routed.edge.to_id,
                node_text_boxes=estimated_text_boxes,
            )
            if new_count < old_count:
                routed.points = simplify_polyline(rerouted)
                routed.style["route"] = "orthogonal"
                routed.style["avoid_obstacles"] = True

    all_segments: Dict[str, List[Segment]] = {r.edge.id: polyline_segments(r.points) for r in routed_edges}

    for routed in routed_edges:
        style = routed.style
        color = normalize_color(style["color"])
        width_px = style["width"]
        draw_polyline(draw, routed.points, color=color, width=width_px, pattern=style["pattern"])
        if style["direction"] != "none" and len(routed.points) >= 2:
            draw_arrowhead(draw, routed.points[-2], routed.points[-1], color=color, width=width_px)
            if style["direction"] == "both":
                draw_arrowhead(draw, routed.points[1], routed.points[0], color=color, width=width_px)

    node_color_by_id, node_category_by_id = category_color_map(nodes=nodes, groups=groups, theme=theme)

    layout_nodes: List[dict] = []
    for node in nodes:
        fill_hex = node.style.get("fill") or node_color_by_id.get(node.id)
        text_hex = node.style.get("text") or (contrast_text_hex(fill_hex) if fill_hex else None)
        fill = parse_color(fill_hex, default_node_fill)
        stroke = parse_color(node.style.get("stroke"), default_node_border)
        text_color = parse_color(text_hex, default_node_text)
        radius = int(max(0, node.style.get("radius", args.corner_radius)))
        border_width = int(max(1, node.style.get("border_width", args.border_width)))
        shadow = bool(node.style.get("shadow", args.shadow))

        if shadow:
            draw.rounded_rectangle(
                [node.x + 4, node.y + 5, node.x + node.width + 4, node.y + node.height + 5],
                radius=max(6, radius),
                fill=(15, 23, 42, 45),
                outline=None,
            )

        draw_node_shape(draw, node=node, fill=fill, stroke=stroke, radius=radius, border_width=border_width)
        text_box = draw_text_centered(draw, node.rect, node.label, normalize_color(text_color), font)
        if text_box:
            node_text_rects[node.id] = text_box

        cx, cy = node.center
        layout_nodes.append(
            {
                "id": node.id,
                "label": node.label,
                "source_ref": node.source_ref,
                "bbox_px": [node.x, node.y, node.width, node.height],
                "center_px": [cx, cy],
                "shape": node.shape,
                "category_key": node_category_by_id.get(node.id),
                "text_bbox_px": [text_box[0], text_box[1], text_box[2] - text_box[0], text_box[3] - text_box[1]] if text_box else None,
            }
        )

    placed_label_rects: List[Rect] = []
    edge_label_boxes: Dict[str, Rect] = {}
    placement_warnings: List[dict] = []
    layout_edges: List[dict] = []

    canvas_rect = (0, 0, width, height)
    node_text_rect_list = list(node_text_rects.values())
    for routed in routed_edges:
        edge = routed.edge
        style = routed.style
        label_box = None
        penalty = 0.0
        conflicts = 0
        label_text = edge.label.strip()
        if label_text:
            tw, th = measure_text(draw, label_text, edge_font)
            label_w = tw + 16
            label_h = th + 10
            label_box, penalty, conflicts = choose_label_rect(
                edge_id=edge.id,
                points=routed.points,
                label_w=label_w,
                label_h=label_h,
                canvas_rect=canvas_rect,
                node_rects=node_rects,
                node_text_rects=node_text_rect_list,
                group_label_rects=group_label_rects,
                placed_label_rects=placed_label_rects,
                all_segments=all_segments,
            )
            placed_label_rects.append(label_box)
            edge_label_boxes[edge.id] = label_box
            x1, y1, x2, y2 = label_box
            draw.rounded_rectangle([x1, y1, x2, y2], radius=8, fill=(255, 255, 255, 220), outline=(203, 213, 225, 255), width=1)
            draw.text((x1 + 8, y1 + 4), label_text, fill=(31, 41, 55), font=edge_font)
            if conflicts > args.label_conflict_threshold:
                placement_warnings.append(
                    {"edge_id": edge.id, "kind": "label_occlusion_risk", "penalty": round(penalty, 2), "conflicts": conflicts}
                )

        layout_edges.append(
            {
                "id": edge.id,
                "from": edge.from_id,
                "to": edge.to_id,
                "source_ref": edge.source_ref,
                "polyline_px": [[p[0], p[1]] for p in routed.points],
                "relation": edge.relation,
                "label": edge.label,
                "label_bbox_px": [label_box[0], label_box[1], label_box[2] - label_box[0], label_box[3] - label_box[1]] if label_box else None,
                "label_placement": {"penalty": round(penalty, 2), "conflicts": conflicts},
                "style": {
                    "pattern": style["pattern"],
                    "route": style["route"],
                    "direction": style["direction"],
                    "width": style["width"],
                    "color": f"#{style['color'][0]:02X}{style['color'][1]:02X}{style['color'][2]:02X}",
                    "avoid_obstacles": style["avoid_obstacles"],
                },
            }
        )

    occlusion = detect_occlusions(
        routed_edges=routed_edges,
        node_text_boxes=node_text_rects,
        edge_label_boxes=edge_label_boxes,
        threshold=args.occlusion_warning_threshold,
    )
    occlusion["placement_warnings"] = placement_warnings

    return {
        "canvas": {"width": width, "height": height, "background": theme["background"]},
        "direction": direction,
        "theme": theme,
        "nodes": layout_nodes,
        "edges": layout_edges,
        "groups": group_layout,
        "occlusion": occlusion,
        "image": img,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render chart DSL JSON to PNG and layout JSON")
    parser.add_argument("--input", required=True, help="Path to chart.dsl.json")
    parser.add_argument("--png", required=True, help="Output PNG path")
    parser.add_argument("--layout", help="Output chart.layout.json path")
    parser.add_argument("--padding", type=int, default=56, help="Canvas padding in pixels")
    parser.add_argument("--columns", type=int, default=4, help="Auto-layout column count")
    parser.add_argument("--background", default="#F6F8FC", help="Canvas background color")
    parser.add_argument("--node-fill", default="#FFFFFF", help="Default node fill color")
    parser.add_argument("--node-border", default="#1E293B", help="Default node border color")
    parser.add_argument("--node-text", default="#0F172A", help="Default node text color")
    parser.add_argument("--edge-color", default="#475569", help="Default edge color")
    parser.add_argument("--font-size", type=int, default=18, help="Node label font size")
    parser.add_argument("--corner-radius", type=int, default=14, help="Node corner radius")
    parser.add_argument("--border-width", type=int, default=2, help="Node border width")
    parser.add_argument("--edge-width", type=int, default=3, help="Default edge width")
    parser.add_argument("--shadow", action="store_true", default=True, help="Enable node shadow")
    parser.add_argument("--no-shadow", action="store_false", dest="shadow", help="Disable node shadow")
    parser.add_argument("--orth-avoid", action="store_true", default=True, help="Enable orthogonal obstacle-avoid routing")
    parser.add_argument("--no-orth-avoid", action="store_false", dest="orth_avoid", help="Disable orthogonal obstacle-avoid routing")
    parser.add_argument("--orth-step", type=int, default=24, help="Grid step for obstacle-avoid routing")
    parser.add_argument("--orth-padding", type=int, default=24, help="Obstacle inflation padding in pixels")
    parser.add_argument("--orth-max-expansions", type=int, default=60000, help="A* max expansions for obstacle routing")
    parser.add_argument("--auto-fix-text-occlusion", action="store_true", default=True, help="Auto-repair orthogonal routes that cross non-target node text")
    parser.add_argument("--no-auto-fix-text-occlusion", action="store_false", dest="auto_fix_text_occlusion", help="Disable auto text-occlusion route repair")
    parser.add_argument("--label-conflict-threshold", type=int, default=2, help="Label conflict count threshold for warning")
    parser.add_argument("--occlusion-warning-threshold", type=int, default=0, help="Occlusion issue threshold before warning status")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    png_path = Path(args.png)
    layout_path = Path(args.layout) if args.layout else png_path.with_name("chart.layout.json")

    with input_path.open("r", encoding="utf-8-sig") as f:
        dsl = json.load(f)

    result = render(dsl, args)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    result["image"].convert("RGB").save(png_path, format="PNG")

    layout = {
        "version": "1.3",
        "canvas": result["canvas"],
        "direction": result["direction"],
        "theme": result["theme"],
        "nodes": result["nodes"],
        "edges": result["edges"],
        "groups": result["groups"],
        "occlusion": result["occlusion"],
    }
    layout_path.parent.mkdir(parents=True, exist_ok=True)
    with layout_path.open("w", encoding="utf-8-sig") as f:
        json.dump(layout, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"[render_png] input={input_path}")
    print(f"[render_png] png={png_path}")
    print(f"[render_png] layout={layout_path}")
    print(f"[render_png] occlusion_status={layout['occlusion']['status']} issues={layout['occlusion']['total_issues']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
