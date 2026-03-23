#!/usr/bin/env python3
"""Run local file-driven rendering pipeline.

Required interface:
- input.md / spec.json
- output.png
- output.svg
- output.tex
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local chart pipeline from spec.json")
    parser.add_argument("--spec", required=True, help="Path to spec.json")
    parser.add_argument("--input-md", help="Optional override path to input.md")
    return parser.parse_args()


def resolve_path(base: Path, value: str | None) -> Path | None:
    if not value:
        return None
    p = Path(value)
    if not p.is_absolute():
        p = (base / p).resolve()
    return p


def run_cmd(name: str, cmd: list[str], cwd: Path) -> dict:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {"name": name, "cmd": cmd, "returncode": proc.returncode, "output": proc.stdout}


def main() -> int:
    args = parse_args()
    spec_path = Path(args.spec).resolve()
    spec_dir = spec_path.parent
    repo_dir = Path(__file__).resolve().parents[1]
    scripts_dir = repo_dir / "scripts"

    with spec_path.open("r", encoding="utf-8-sig") as f:
        spec = json.load(f)

    dsl_path = resolve_path(spec_dir, str(spec.get("dsl", "")))
    if dsl_path is None or not dsl_path.exists():
        raise FileNotFoundError("spec.json must include existing field: dsl")
    color_plan_path = resolve_path(spec_dir, spec.get("color_plan"))
    if color_plan_path and not color_plan_path.exists():
        raise FileNotFoundError(f"color_plan file not found: {color_plan_path}")

    output_dir = resolve_path(spec_dir, str(spec.get("output_dir", "output")))
    assert output_dir is not None
    output_dir.mkdir(parents=True, exist_ok=True)
    basename = str(spec.get("basename", "output"))

    formats = set(spec.get("formats", ["png", "svg", "tex"]))
    compile_pdf = bool(spec.get("tikz_compile", False) or "pdf" in formats)
    tikz_engine = str(spec.get("tikz_engine", "auto"))

    input_md_path = resolve_path(spec_dir, args.input_md or spec.get("input_md"))
    input_md_exists = bool(input_md_path and input_md_path.exists())

    output_png = output_dir / f"{basename}.png"
    output_layout = output_dir / f"{basename}.layout.json"
    output_occlusion = output_dir / f"{basename}.occlusion.json"
    output_map = output_dir / f"{basename}.map.json"
    output_svg = output_dir / f"{basename}.svg"
    output_tex = output_dir / f"{basename}.tex"
    output_colored_dsl = output_dir / f"{basename}.colored.dsl.json"

    results: list[dict] = []
    failed_steps: list[str] = []
    occlusion_gate_failed = False
    effective_dsl_path = dsl_path

    # 1) Optional color-plan apply (LLM-produced)
    if color_plan_path:
        results.append(
            run_cmd(
                "apply_color_plan",
                [
                    sys.executable,
                    str(scripts_dir / "apply_color_plan.py"),
                    "--dsl",
                    str(dsl_path),
                    "--plan",
                    str(color_plan_path),
                    "--output",
                    str(output_colored_dsl),
                ],
                cwd=repo_dir,
            )
        )
        if results[-1]["returncode"] != 0:
            failed_steps.append("apply_color_plan")
        else:
            effective_dsl_path = output_colored_dsl

    # 2) PNG + layout
    if not failed_steps:
        results.append(
            run_cmd(
                "render_png",
                [
                    sys.executable,
                    str(scripts_dir / "render_png.py"),
                    "--input",
                    str(effective_dsl_path),
                    "--png",
                    str(output_png),
                    "--layout",
                    str(output_layout),
                ],
                cwd=repo_dir,
            )
        )
        if results[-1]["returncode"] != 0:
            failed_steps.append("render_png")

    # 3) Source-visual mapping
    if not failed_steps:
        results.append(
            run_cmd(
                "export_mapping",
                [
                    sys.executable,
                    str(scripts_dir / "export_mapping.py"),
                    "--source",
                    str(effective_dsl_path),
                    "--layout",
                    str(output_layout),
                    "--output",
                    str(output_map),
                ],
                cwd=repo_dir,
            )
        )
        if results[-1]["returncode"] != 0:
            failed_steps.append("export_mapping")

    # 4) Occlusion analysis
    if not failed_steps:
        results.append(
            run_cmd(
                "analyze_occlusion",
                [
                    sys.executable,
                    str(scripts_dir / "analyze_occlusion.py"),
                    "--layout",
                    str(output_layout),
                    "--output",
                    str(output_occlusion),
                    "--max-issues",
                    str(spec.get("max_occlusion_issues", 0)),
                ],
                cwd=repo_dir,
            )
        )
        occlusion_gate_failed = results[-1]["returncode"] != 0

        # 5) SVG export
        if "svg" in formats:
            results.append(
                run_cmd(
                    "render_svg",
                    [
                        sys.executable,
                        str(scripts_dir / "render_svg.py"),
                        "--source",
                        str(effective_dsl_path),
                        "--layout",
                        str(output_layout),
                        "--output",
                        str(output_svg),
                    ],
                    cwd=repo_dir,
                )
            )
            if results[-1]["returncode"] != 0:
                failed_steps.append("render_svg")

        # 6) TikZ export
        if "tex" in formats or compile_pdf:
            results.append(
                run_cmd(
                    "render_tikz",
                    [
                        sys.executable,
                        str(scripts_dir / "render_tikz.py"),
                        "--source",
                        str(effective_dsl_path),
                        "--layout",
                        str(output_layout),
                        "--output",
                        str(output_tex),
                    ],
                    cwd=repo_dir,
                )
            )
            if results[-1]["returncode"] != 0:
                failed_steps.append("render_tikz")

        # 7) TikZ compile chain (optional)
        if compile_pdf and not failed_steps:
            results.append(
                run_cmd(
                    "render_tikz_chain",
                    [
                        sys.executable,
                        str(scripts_dir / "render_tikz_chain.py"),
                        "--tex",
                        str(output_tex),
                        "--output-dir",
                        str(output_dir),
                        "--basename",
                        basename,
                        "--engine",
                        tikz_engine,
                    ],
                    cwd=repo_dir,
                )
            )
            if results[-1]["returncode"] != 0:
                failed_steps.append("render_tikz_chain")

    status = "failed" if failed_steps else ("warning" if occlusion_gate_failed else "ok")

    manifest = {
        "status": status,
        "spec": str(spec_path),
        "input_md": str(input_md_path) if input_md_path else None,
        "input_md_exists": input_md_exists,
        "dsl": str(dsl_path),
        "effective_dsl": str(effective_dsl_path),
        "color_plan": str(color_plan_path) if color_plan_path else None,
        "occlusion_gate_failed": occlusion_gate_failed,
        "failed_steps": failed_steps,
        "outputs": {
            "colored_dsl": str(output_colored_dsl) if output_colored_dsl.exists() else None,
            "png": str(output_png) if output_png.exists() else None,
            "layout": str(output_layout) if output_layout.exists() else None,
            "occlusion": str(output_occlusion) if output_occlusion.exists() else None,
            "map": str(output_map) if output_map.exists() else None,
            "svg": str(output_svg) if output_svg.exists() else None,
            "tex": str(output_tex) if output_tex.exists() else None,
            "pdf": str(output_dir / f"{basename}.pdf") if (output_dir / f"{basename}.pdf").exists() else None,
            "png_from_tex": str(output_dir / f"{basename}.from_tex.png")
            if (output_dir / f"{basename}.from_tex.png").exists()
            else None,
            "tikz_log": str(output_dir / f"{basename}.render.log")
            if (output_dir / f"{basename}.render.log").exists()
            else None,
            "tikz_status": str(output_dir / f"{basename}.render.status.json")
            if (output_dir / f"{basename}.render.status.json").exists()
            else None,
        },
        "steps": results,
    }
    manifest_path = output_dir / f"{basename}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"[run_local_pipeline] spec={spec_path}")
    print(f"[run_local_pipeline] status={status}")
    print(f"[run_local_pipeline] manifest={manifest_path}")

    if failed_steps:
        return 3
    if occlusion_gate_failed:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
