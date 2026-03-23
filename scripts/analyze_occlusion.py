#!/usr/bin/env python3
"""Analyze occlusion risks in chart layout output.

Checks:
- edge segments crossing node text boxes
- edge label boxes overlapping node text boxes
- edge label boxes overlapping each other
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple


Point = Tuple[int, int]
Rect = Tuple[int, int, int, int]
Segment = Tuple[Point, Point]


def rect_from_xywh(values: list[int] | None) -> Rect | None:
    if not values or len(values) != 4:
        return None
    x, y, w, h = values
    return (int(x), int(y), int(x + w), int(y + h))


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


def poly_segments(points: list[list[int]]) -> List[Segment]:
    if len(points) < 2:
        return []
    pairs: List[Segment] = []
    for i in range(len(points) - 1):
        a = points[i]
        b = points[i + 1]
        pairs.append(((int(a[0]), int(a[1])), (int(b[0]), int(b[1]))))
    return pairs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze occlusion in chart.layout.json")
    parser.add_argument("--layout", required=True, help="Path to chart.layout.json")
    parser.add_argument("--output", required=True, help="Path to occlusion report JSON")
    parser.add_argument("--max-issues", type=int, default=0, help="Fail when issue count exceeds this threshold")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    layout_path = Path(args.layout)
    output_path = Path(args.output)

    with layout_path.open("r", encoding="utf-8-sig") as f:
        layout = json.load(f)

    node_text_boxes: Dict[str, Rect] = {}
    for node in layout.get("nodes", []):
        rect = rect_from_xywh(node.get("text_bbox_px"))
        if rect:
            node_text_boxes[str(node.get("id", ""))] = rect

    edge_label_boxes: Dict[str, Rect] = {}
    edge_segments: Dict[str, List[Segment]] = {}
    edge_endpoints: Dict[str, Tuple[str, str]] = {}
    for edge in layout.get("edges", []):
        edge_id = str(edge.get("id", ""))
        if not edge_id:
            continue
        label_rect = rect_from_xywh(edge.get("label_bbox_px"))
        if label_rect:
            edge_label_boxes[edge_id] = label_rect
        edge_segments[edge_id] = poly_segments(edge.get("polyline_px", []))
        edge_endpoints[edge_id] = (str(edge.get("from", "")), str(edge.get("to", "")))

    issues: List[dict] = []

    for edge_id, segments in edge_segments.items():
        from_id, to_id = edge_endpoints[edge_id]
        for seg in segments:
            for node_id, rect in node_text_boxes.items():
                if node_id in {from_id, to_id}:
                    continue
                if segment_intersects_rect(seg, rect):
                    issues.append(
                        {
                            "type": "edge_vs_node_text",
                            "edge_id": edge_id,
                            "node_id": node_id,
                        }
                    )

    for edge_id, label_rect in edge_label_boxes.items():
        for node_id, text_rect in node_text_boxes.items():
            if rect_overlap_area(label_rect, text_rect) > 0:
                issues.append(
                    {
                        "type": "edge_label_vs_node_text",
                        "edge_id": edge_id,
                        "node_id": node_id,
                    }
                )

    sorted_edge_ids = sorted(edge_label_boxes.keys())
    for i in range(len(sorted_edge_ids)):
        for j in range(i + 1, len(sorted_edge_ids)):
            a = sorted_edge_ids[i]
            b = sorted_edge_ids[j]
            if rect_overlap_area(edge_label_boxes[a], edge_label_boxes[b]) > 0:
                issues.append(
                    {
                        "type": "edge_label_vs_edge_label",
                        "edge_a": a,
                        "edge_b": b,
                    }
                )

    report = {
        "layout_file": str(layout_path),
        "issue_count": len(issues),
        "status": "ok" if len(issues) <= args.max_issues else "warning",
        "issues": issues[:500],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"[analyze_occlusion] layout={layout_path}")
    print(f"[analyze_occlusion] output={output_path}")
    print(f"[analyze_occlusion] issues={report['issue_count']} status={report['status']}")

    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
