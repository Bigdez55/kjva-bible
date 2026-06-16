#!/usr/bin/env python3
"""
wired_audit.py — Honest DEFINED / IMPORTED / CALLED audit of a Python codebase.

Walks a repo to enumerate every .py module (DEFINED), runs a user-supplied
entrypoint expression with sys.settrace + sys.modules snapshots active to
measure what is actually IMPORTED and CALLED on the canonical runtime path.

Single file, stdlib only, Python 3.10+. coverage.py is used opportunistically
if installed, but settrace is the authoritative CALLED source (it fires
directly on every function-entry frame, which is exactly what we want).

Self-test:
    python3 wired_audit.py --self-test
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import inspect
import json
import os
import sys
import tempfile
import textwrap
import traceback
from pathlib import Path
from typing import Any


# ---------- DEFINED: walk repo, build filename -> dotted-name map -----------

def _is_repo_local(real_path: str, repo_real: str) -> bool:
    return real_path.startswith(repo_real + os.sep) or real_path == repo_real


def walk_defined(repo_real: str) -> tuple[dict[str, str], set[str]]:
    """Return (filename_to_dotted, top_level_folders).

    Keys are os.path.realpath() of each .py file so they survive symlinks
    (OneDrive CloudStorage paths are symlinks on macOS).
    """
    filename_to_dotted: dict[str, str] = {}
    top_folders: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(repo_real):
        # prune hidden + virtualenv + cache dirs
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".")
            and d not in {"__pycache__", "node_modules", ".venv", "venv", "build", "dist"}
        ]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            full = os.path.realpath(os.path.join(dirpath, fn))
            rel = os.path.relpath(full, repo_real)
            parts = rel.split(os.sep)
            # top-level folders are only directories, not loose .py files
            if len(parts) > 1:
                top_folders.add(parts[0])
            # repo root itself is not a package — skip a stray top-level __init__.py
            if len(parts) == 1 and fn == "__init__.py":
                continue
            # dotted name relative to repo root, strip .py and __init__
            dotted_parts = parts[:]
            dotted_parts[-1] = dotted_parts[-1][:-3]  # strip .py
            if dotted_parts[-1] == "__init__":
                dotted_parts = dotted_parts[:-1]
            dotted = ".".join(p for p in dotted_parts if p)
            if dotted:
                filename_to_dotted[full] = dotted
    return filename_to_dotted, top_folders


# ---------- entrypoint runner: AST-split for async, settrace for CALLED -----

def _build_tracer(filename_to_dotted: dict[str, str], called: set[tuple[str, str]]):
    """Return a settrace callback that records repo-local function calls.

    Defensive: any exception inside the tracer silently disables tracing,
    so we swallow everything. Only the calling thread is traced (limitation).
    """
    fmap = filename_to_dotted

    def tracer(frame, event, arg):
        try:
            if event == "call":
                name = frame.f_code.co_name
                # module-body execution registers as a 'call' event with
                # co_name == '<module>'; that is import-time, not a function
                # call, so skip it.
                if name == "<module>":
                    return tracer
                fn = frame.f_code.co_filename
                real = os.path.realpath(fn) if fn else ""
                dotted = fmap.get(real)
                if dotted is not None:
                    called.add((dotted, name))
        except Exception:
            pass
        return tracer

    return tracer


def _split_entrypoint(src: str) -> tuple[str, str | None]:
    """Return (prefix_to_exec, trailing_expr_to_eval_or_None).

    If the source ends in an expression statement, peel it off so we can
    eval() it and inspect the return value for a coroutine. Otherwise
    everything runs under exec().
    """
    tree = ast.parse(src, mode="exec")
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last = tree.body[-1]
        prefix = ast.Module(body=tree.body[:-1], type_ignores=[])
        prefix_src = ast.unparse(prefix) if prefix.body else ""
        expr_src = ast.unparse(last.value)
        return prefix_src, expr_src
    return src, None


def run_entrypoint(
    repo_real: str,
    entrypoint: str,
    filename_to_dotted: dict[str, str],
) -> tuple[set[str], set[tuple[str, str]], str | None]:
    """Execute entrypoint with tracing + sys.modules diffing.

    Returns (imported_dotted_set, called_pairs, error_or_None).
    On exception we still return whatever was captured up to that point.
    """
    before = set(sys.modules.keys())
    called: set[tuple[str, str]] = set()
    err: str | None = None

    saved_path = list(sys.path)
    saved_tracer = sys.gettrace()

    # opportunistic coverage (informational only; settrace is authoritative)
    cov = None
    try:
        import coverage  # type: ignore
        cov = coverage.Coverage(source=[repo_real])
        cov.start()
    except Exception:
        cov = None

    sys.path.insert(0, repo_real)
    tracer = _build_tracer(filename_to_dotted, called)

    try:
        ns: dict[str, Any] = {"__name__": "__wired_audit_entry__"}
        prefix_src, expr_src = _split_entrypoint(entrypoint)
        sys.settrace(tracer)
        try:
            if prefix_src.strip():
                exec(compile(prefix_src, "<entrypoint-prefix>", "exec"), ns)
            if expr_src is not None:
                result = eval(compile(expr_src, "<entrypoint-expr>", "eval"), ns)
                if inspect.iscoroutine(result):
                    asyncio.run(result)
        finally:
            sys.settrace(saved_tracer)
    except Exception:
        err = traceback.format_exc()
    finally:
        sys.path[:] = saved_path
        if cov is not None:
            try:
                cov.stop()
            except Exception:
                pass

    after = set(sys.modules.keys())
    imported_dotted: set[str] = set()
    repo_real_norm = repo_real
    for name in after - before:
        mod = sys.modules.get(name)
        if mod is None:
            continue
        f = getattr(mod, "__file__", None)
        if not f:
            continue
        real = os.path.realpath(f)
        if _is_repo_local(real, repo_real_norm):
            dotted = filename_to_dotted.get(real)
            if dotted:
                imported_dotted.add(dotted)
    return imported_dotted, called, err


# ---------- analysis + reporting --------------------------------------------

def run_audit(repo: str, entrypoint: str, required: list[str]) -> dict[str, Any]:
    repo_real = os.path.realpath(repo)
    if not os.path.isdir(repo_real):
        raise SystemExit(f"repo not found: {repo}")

    filename_to_dotted, top_folders = walk_defined(repo_real)
    defined_dotted = set(filename_to_dotted.values())

    imported, called_pairs, err = run_entrypoint(repo_real, entrypoint, filename_to_dotted)

    called_modules = {m for (m, _f) in called_pairs}
    imported_only = sorted(imported - called_modules)
    dead_modules = sorted(defined_dotted - imported)

    # DEAD folder = no module under that top-level folder was imported
    imported_top = {d.split(".", 1)[0] for d in imported}
    dead_folders = sorted(top_folders - imported_top)

    # Coverage choice (documented): K/N as spec labels it = called-pair count /
    # defined module count. We also surface the more meaningful module-level
    # coverage (called_modules / defined_modules).
    n_defined = len(defined_dotted)
    k_called_pairs = len(called_pairs)
    module_coverage = (len(called_modules) / n_defined) if n_defined else 0.0

    # required-pillar gate: a pillar passes if >=1 called module starts with it
    failures: list[dict[str, str]] = []
    for pillar in required:
        pillar = pillar.strip()
        if not pillar:
            continue
        hits = [m for m in called_modules if m == pillar or m.startswith(pillar + ".")]
        imp_hits = [m for m in imported if m == pillar or m.startswith(pillar + ".")]
        if hits:
            status = "CALLED"
        elif imp_hits:
            status = "IMPORTED_ONLY"
        else:
            status = "DEAD"
        failures.append({"pillar": pillar, "status": status})

    return {
        "repo": repo_real,
        "entrypoint": entrypoint,
        "defined_modules": sorted(defined_dotted),
        "defined_folders": sorted(top_folders),
        "imported_modules": sorted(imported),
        "called_pairs": sorted([f"{m}:{f}" for m, f in called_pairs]),
        "called_modules": sorted(called_modules),
        "dead_folders": dead_folders,
        "dead_modules": dead_modules,
        "imported_only_modules": imported_only,
        "counts": {
            "defined": n_defined,
            "imported": len(imported),
            "called_pairs": k_called_pairs,
            "called_modules": len(called_modules),
        },
        "module_coverage_ratio": module_coverage,
        "required_pillars": failures,
        "entrypoint_error": err,
    }


def render_markdown(r: dict[str, Any]) -> str:
    c = r["counts"]
    lines: list[str] = []
    lines.append(f"# Wired Audit — {r['repo']}")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|---|---|")
    lines.append(f"| DEFINED folders | {len(r['defined_folders'])} |")
    lines.append(f"| DEFINED modules | {c['defined']} |")
    lines.append(f"| IMPORTED at runtime | {c['imported']} |")
    lines.append(f"| CALLED during entrypoint (pairs K) | {c['called_pairs']} |")
    lines.append(f"| CALLED modules (distinct) | {c['called_modules']} |")
    lines.append(f"| Module coverage (called/defined) | {r['module_coverage_ratio']:.1%} |")
    lines.append("")
    lines.append("## DEAD folders (no module imported)")
    lines.append("\n".join(f"- {d}" for d in r["dead_folders"]) or "_none_")
    lines.append("")
    lines.append("## IMPORTED-ONLY modules (no function called)")
    lines.append("\n".join(f"- {m}" for m in r["imported_only_modules"]) or "_none_")
    lines.append("")
    if r["required_pillars"]:
        lines.append("## Required pillars")
        lines.append("| Pillar | Status |")
        lines.append("|---|---|")
        for p in r["required_pillars"]:
            lines.append(f"| {p['pillar']} | {p['status']} |")
        lines.append("")
    if r["entrypoint_error"]:
        lines.append("## Entrypoint error (audit captured partial results)")
        lines.append("```")
        lines.append(r["entrypoint_error"].rstrip())
        lines.append("```")
    return "\n".join(lines)


# ---------- self-test --------------------------------------------------------

def self_test() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "synthrepo"
        (root / "orphan").mkdir(parents=True)
        (root / "live_pkg").mkdir()
        (root / "__init__.py").write_text("")
        (root / "live_pkg" / "__init__.py").write_text("")
        (root / "live_pkg" / "live.py").write_text(textwrap.dedent("""
            def used():
                return 42
            def unused():
                return 0
        """).strip())
        (root / "orphan" / "__init__.py").write_text("")
        (root / "orphan" / "dead_mod.py").write_text("def never(): return 1")
        (root / "imported_only.py").write_text("HELLO = 'hi'")

        entrypoint = (
            "import imported_only\n"
            "from live_pkg.live import used\n"
            "used()\n"
        )
        result = run_audit(str(root), entrypoint, required=["live_pkg.live", "orphan.dead_mod"])

        assert "orphan.dead_mod" in result["dead_modules"], result["dead_modules"]
        assert "orphan" in result["dead_folders"], result["dead_folders"]
        assert "imported_only" in result["imported_only_modules"], result["imported_only_modules"]
        assert "live_pkg.live" in result["called_modules"], result["called_modules"]

        statuses = {p["pillar"]: p["status"] for p in result["required_pillars"]}
        assert statuses["live_pkg.live"] == "CALLED", statuses
        assert statuses["orphan.dead_mod"] == "DEAD", statuses

        print("self-test: OK")
        return 0


# ---------- CLI --------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Honest DEFINED / IMPORTED / CALLED audit")
    ap.add_argument("--repo", help="path to repository root")
    ap.add_argument("--entrypoint", help="python expression that triggers the canonical runtime")
    ap.add_argument("--report", choices=["json", "markdown"], default="markdown")
    ap.add_argument("--required", default="", help="comma-separated dotted pillars that must be CALLED")
    ap.add_argument("--self-test", action="store_true", help="run built-in self-test and exit")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if not args.repo or not args.entrypoint:
        ap.error("--repo and --entrypoint are required (or use --self-test)")

    required = [p for p in args.required.split(",") if p.strip()]
    result = run_audit(args.repo, args.entrypoint, required)

    if args.report == "json":
        print(json.dumps(result, indent=2))
    else:
        print(render_markdown(result))

    bad = [p for p in result["required_pillars"] if p["status"] != "CALLED"]
    if bad:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
