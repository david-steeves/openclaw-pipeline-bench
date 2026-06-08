"""
Reads bench/results/<timestamp>/*/run-*.json and produces a Markdown REPORT.

Usage:
    python scripts/generate_report.py bench/results/<timestamp>

Output goes to stdout (Makefile redirects to REPORT.md).
"""

import json
import statistics
import sys
from pathlib import Path


VARIANT_ORDER = ["baseline", "pipeline-noop", "pipeline-1-analyst", "pipeline-blocking"]


def collect(results_dir: Path) -> dict[str, list[dict]]:
    runs: dict[str, list[dict]] = {v: [] for v in VARIANT_ORDER}
    for variant in VARIANT_ORDER:
        vdir = results_dir / variant
        if not vdir.exists():
            continue
        for run_file in sorted(vdir.glob("run-*.json")):
            with open(run_file) as f:
                runs[variant].append(json.load(f))
    return runs


def summarize_runs(runs: list[dict]) -> dict:
    if not runs:
        return {}
    p50s = [r["latency_ms"]["p50"] for r in runs if r["latency_ms"]["p50"] is not None]
    p95s = [r["latency_ms"]["p95"] for r in runs if r["latency_ms"]["p95"] is not None]
    p99s = [r["latency_ms"]["p99"] for r in runs if r["latency_ms"]["p99"] is not None]
    rss = [r["rss_mb"]["peak"] for r in runs if r["rss_mb"]["peak"] is not None]
    tps = [r["throughput_eps"] for r in runs]
    cold = [r["cold_start_ms"] for r in runs]
    blocks = [r["events_blocked"] for r in runs]

    def m(xs):
        return statistics.median(xs) if xs else None

    return {
        "runs": len(runs),
        "p50_median_ms": m(p50s),
        "p95_median_ms": m(p95s),
        "p99_median_ms": m(p99s),
        "rss_peak_median_mb": m(rss),
        "throughput_median_eps": m(tps),
        "cold_start_median_ms": m(cold),
        "blocks_median": m(blocks),
    }


def fmt(v, suffix=""):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.2f}{suffix}"
    return f"{v}{suffix}"


def render(results_dir: Path, summaries: dict[str, dict]) -> str:
    lines = []
    lines.append(f"# openclaw-pipeline-bench — REPORT")
    lines.append("")
    lines.append(f"**Results dir:** `{results_dir}`")
    lines.append(f"**Companion RFC:** [openclaw/rfcs#11](https://github.com/openclaw/rfcs/pull/11)")
    lines.append("")
    lines.append("## Headline")
    lines.append("")
    lines.append("> _Write 1 paragraph by hand here — the human read of the table below._")
    lines.append("")
    lines.append("## Results (median of 3 runs)")
    lines.append("")
    lines.append("| Variant | Runs | p50 ms | p95 ms | p99 ms | RSS peak MB | Throughput eps | Cold start ms | Blocked |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for v in VARIANT_ORDER:
        s = summaries.get(v) or {}
        lines.append("| {variant} | {runs} | {p50} | {p95} | {p99} | {rss} | {tps} | {cold} | {blk} |".format(
            variant=v,
            runs=s.get("runs", 0),
            p50=fmt(s.get("p50_median_ms")),
            p95=fmt(s.get("p95_median_ms")),
            p99=fmt(s.get("p99_median_ms")),
            rss=fmt(s.get("rss_peak_median_mb")),
            tps=fmt(s.get("throughput_median_eps")),
            cold=fmt(s.get("cold_start_median_ms")),
            blk=fmt(s.get("blocks_median")),
        ))
    lines.append("")
    lines.append("## Sanity gates (per design step 6)")
    lines.append("")
    lines.append("- [ ] baseline ≈ pipeline-noop within an order of magnitude")
    lines.append("- [ ] pipeline-1-analyst ≈ pipeline-noop + (2 × analyst cost_ms)")
    lines.append("- [ ] pipeline-blocking shows non-zero `Blocked` count")
    lines.append("")
    lines.append("If any gate fails, do not share numbers until investigated.")
    return "\n".join(lines)


def main():
    if len(sys.argv) != 2:
        print("usage: generate_report.py <results_dir>", file=sys.stderr)
        sys.exit(2)
    results_dir = Path(sys.argv[1])
    runs = collect(results_dir)
    summaries = {v: summarize_runs(rs) for v, rs in runs.items()}
    print(render(results_dir, summaries))


if __name__ == "__main__":
    main()
