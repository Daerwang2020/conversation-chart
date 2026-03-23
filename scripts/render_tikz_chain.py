#!/usr/bin/env python3
"""Compile TikZ LaTeX and optionally export PNG.

Pipeline:
- tectonic or pdflatex -> PDF
- pdftoppm or magick -> PNG
- write status + logs
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compile TikZ .tex to PDF/PNG")
    parser.add_argument("--tex", required=True, help="Path to .tex file")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--basename", default="output", help="Output basename")
    parser.add_argument("--engine", default="auto", choices=["auto", "tectonic", "pdflatex"], help="LaTeX engine")
    parser.add_argument("--skip-png", action="store_true", help="Skip PDF->PNG conversion")
    return parser.parse_args()


def run_command(cmd: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout


def main() -> int:
    args = parse_args()
    tex_path = Path(args.tex).resolve()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    log_path = out_dir / f"{args.basename}.render.log"
    status_path = out_dir / f"{args.basename}.render.status.json"
    pdf_path = out_dir / f"{args.basename}.pdf"
    png_path = out_dir / f"{args.basename}.from_tex.png"

    logs: list[str] = []
    compile_ok = False
    engine_used = None

    engines: list[str]
    if args.engine == "auto":
        engines = ["tectonic", "pdflatex"]
    else:
        engines = [args.engine]

    for engine in engines:
        if shutil.which(engine) is None:
            logs.append(f"[compile] skip {engine}: executable not found")
            continue
        if engine == "tectonic":
            cmd = ["tectonic", "--outdir", str(out_dir), str(tex_path)]
        else:
            cmd = [
                "pdflatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                f"-output-directory={out_dir}",
                str(tex_path),
            ]
        code, output = run_command(cmd, cwd=out_dir)
        logs.append(f"$ {' '.join(cmd)}")
        logs.append(output)
        if code == 0:
            compile_ok = True
            engine_used = engine
            break

    if compile_ok and not pdf_path.exists():
        alt_pdf = tex_path.with_suffix(".pdf")
        if alt_pdf.exists():
            alt_pdf.replace(pdf_path)

    png_ok = False
    if compile_ok and not args.skip_png:
        if shutil.which("pdftoppm"):
            cmd = ["pdftoppm", "-singlefile", "-png", str(pdf_path), str(png_path.with_suffix(""))]
            code, output = run_command(cmd, cwd=out_dir)
            logs.append(f"$ {' '.join(cmd)}")
            logs.append(output)
            png_ok = code == 0 and png_path.exists()
        elif shutil.which("magick"):
            cmd = ["magick", "-density", "300", f"{pdf_path}[0]", str(png_path)]
            code, output = run_command(cmd, cwd=out_dir)
            logs.append(f"$ {' '.join(cmd)}")
            logs.append(output)
            png_ok = code == 0 and png_path.exists()
        else:
            logs.append("[png] skip conversion: neither pdftoppm nor magick found")

    log_path.write_text("\n".join(logs) + "\n", encoding="utf-8")
    status = {
        "tex": str(tex_path),
        "pdf": str(pdf_path) if pdf_path.exists() else None,
        "png": str(png_path) if png_path.exists() else None,
        "engine": engine_used,
        "compile_ok": compile_ok,
        "png_ok": png_ok,
        "log_file": str(log_path),
    }
    status_path.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"[render_tikz_chain] tex={tex_path}")
    print(f"[render_tikz_chain] status={status_path}")
    print(f"[render_tikz_chain] compile_ok={compile_ok} png_ok={png_ok}")
    return 0 if compile_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
