#!/usr/bin/env python3
"""Export source-to-visual mapping for conversation charts.

Reads chart.dsl.json and chart.layout.json, then writes chart.map.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Dict, List


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def build_index(items: List[dict], key: str) -> Dict[str, dict]:
    index: Dict[str, dict] = {}
    for obj in items:
        obj_id = str(obj.get(key, "")).strip()
        if not obj_id:
            continue
        index[obj_id] = obj
    return index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export chart.map.json from source and layout")
    parser.add_argument("--source", required=True, help="Path to chart.dsl.json")
    parser.add_argument("--layout", required=True, help="Path to chart.layout.json")
    parser.add_argument("--output", required=True, help="Path to chart.map.json")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any source node/edge cannot be found in layout",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_path = Path(args.source)
    layout_path = Path(args.layout)
    output_path = Path(args.output)

    with source_path.open("r", encoding="utf-8-sig") as f:
        source = json.load(f)

    with layout_path.open("r", encoding="utf-8-sig") as f:
        layout = json.load(f)

    source_nodes = source.get("nodes", [])
    source_edges = source.get("edges", [])
    layout_nodes = layout.get("nodes", [])
    layout_edges = layout.get("edges", [])

    node_geo = build_index(layout_nodes, "id")
    edge_geo = build_index(layout_edges, "id")

    warnings: List[str] = []
    nodes_out: List[dict] = []
    edges_out: List[dict] = []

    for i, node in enumerate(source_nodes):
        node_id = str(node.get("id", "")).strip()
        if not node_id:
            warnings.append(f"source node at index {i} is missing id")
            continue

        geo = node_geo.get(node_id)
        present = geo is not None
        if not present:
            msg = f"node '{node_id}' not present in layout"
            warnings.append(msg)
            if args.strict:
                raise ValueError(msg)

        nodes_out.append(
            {
                "id": node_id,
                "label": str(node.get("label", "")),
                "source_ref": f"nodes[{i}]",
                "bbox_px": geo.get("bbox_px") if geo else None,
                "center_px": geo.get("center_px") if geo else None,
                "present_in_png": present,
            }
        )

    for i, edge in enumerate(source_edges):
        edge_id = str(edge.get("id", "")).strip()
        if not edge_id:
            warnings.append(f"source edge at index {i} is missing id")
            continue

        geo = edge_geo.get(edge_id)
        present = geo is not None
        if not present:
            msg = f"edge '{edge_id}' not present in layout"
            warnings.append(msg)
            if args.strict:
                raise ValueError(msg)

        edges_out.append(
            {
                "id": edge_id,
                "from": str(edge.get("from", "")),
                "to": str(edge.get("to", "")),
                "source_ref": f"edges[{i}]",
                "polyline_px": geo.get("polyline_px") if geo else None,
                "present_in_png": present,
            }
        )

    output = {
        "version": "1.0",
        "source_file": str(source_path),
        "layout_file": str(layout_path),
        "source_sha256": sha256_file(source_path),
        "nodes": nodes_out,
        "edges": edges_out,
        "warnings": warnings,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"[export_mapping] source={source_path}")
    print(f"[export_mapping] layout={layout_path}")
    print(f"[export_mapping] output={output_path}")
    print(f"[export_mapping] warnings={len(warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
