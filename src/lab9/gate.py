"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS

COUNT_METRICS = {"secret_leak", "approval_bypass"}   # lab9.eval.aggregate sums these, averages the rest


def _is_nan(v) -> bool:
    return isinstance(v, float) and (math.isnan(v) or math.isinf(v))


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]
    rows = pr.get("rows") or []
    base_rows = base.get("rows") or []
    man, base_man = pr.get("manifest") or {}, base.get("manifest") or {}

    # 1. Values a threshold cannot judge (NaN < min is False, so a naive gate passes them).
    for k, v in (pr.get("metrics") or {}).items():
        if _is_nan(v):
            problems.append(f"metric {k} is {v}")

    # 2. Row count must match the manifest; no (item, seed) twice.
    want_n = int(man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want_n:
        problems.append(f"{len(rows)} rows, manifest says {man.get('items')} items x "
                        f"{len(man.get('seeds') or [])} seeds = {want_n}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    seen, dups = set(), set()
    for k in keys:
        (dups if k in seen else seen).add(k)
    if dups:
        problems.append(f"duplicated (item, seed) rows: {sorted(dups, key=str)[:5]}")

    # 3. Same items, seeds and (item, seed) set as the baseline (no cherry-picking).
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    missing, extra = base_keys - seen, seen - base_keys
    if missing or extra:
        problems.append(f"(item, seed) set differs from baseline: {len(missing)} missing, {len(extra)} extra")
    if sorted(man.get("seeds") or []) != sorted(base_man.get("seeds") or []):
        problems.append(f"seeds {man.get('seeds')} differ from baseline {base_man.get('seeds')}")
    if man.get("items") != base_man.get("items"):
        problems.append(f"items {man.get('items')} differ from baseline {base_man.get('items')}")

    # 4. Crashed graders: a failure list, or a graded value that is None/NaN/absent on a row.
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s): {pr['evaluator_failures'][0]}")
    base_graded = {m for m in graded if base_rows and m in base_rows[0]}
    holes = [(r.get("item_id"), r.get("seed"), m) for r in rows for m in graded
             if (m in r and (r[m] is None or _is_nan(r[m]))) or (m not in r and m in base_graded)]
    if holes:
        problems.append(f"{len(holes)} graded value(s) missing, first {holes[0]}")

    # 5. Reported metrics must equal what the rows say (hand-edited or stale aggregates).
    for m in graded:
        vals = [bool(r[m]) for r in rows if m in r and r[m] is not None and not _is_nan(r[m])]
        if not vals or m not in (pr.get("metrics") or {}):
            continue
        want = sum(vals) if m in COUNT_METRICS else round(sum(vals) / len(vals), 4)
        got = pr["metrics"][m]
        if isinstance(got, bool) or not isinstance(got, (int, float)) or _is_nan(got) or abs(float(got) - want) > 1e-4:
            problems.append(f"metric {m} reported {got} but rows give {want}")

    # 6. An item's slice tags must match the baseline's (relabelling hides a slice regression).
    base_slices = {r.get("item_id"): sorted(r.get("slices") or []) for r in base_rows}
    moved = sorted({r.get("item_id") for r in rows if r.get("item_id") in base_slices
                    and sorted(r.get("slices") or []) != base_slices[r.get("item_id")]})
    if moved:
        problems.append(f"slice tags differ from baseline for {moved[:5]}")

    # 7. Ratchet: same eval-set version => thresholds may only get stricter.
    if base_spec is not None and base_spec.get("eval_set_version") == spec.get("eval_set_version"):
        problems += _ratchet(base_spec, spec)
    return problems


def _looser(old: dict, new: dict) -> list[str]:
    """Threshold keys on which `new` is laxer than `old`."""
    out = []
    for key in ("min", "max", "max_increase"):
        if key not in old:
            continue
        if key not in new:
            out.append(f"{key} removed")
        elif key == "min" and new[key] < old[key]:
            out.append(f"min {old[key]} -> {new[key]}")
        elif key != "min" and new[key] > old[key]:
            out.append(f"{key} {old[key]} -> {new[key]}")
    if old.get("no_significant_drop") and not new.get("no_significant_drop"):
        out.append("no_significant_drop dropped")
    return out


def _ratchet(base_spec: dict, spec: dict) -> list[str]:
    problems = []
    new_metrics = {m["id"]: m for m in spec.get("metrics") or []}
    for m in base_spec.get("metrics") or []:
        n = new_metrics.get(m["id"])
        if n is None:
            problems.append(f"ratchet: metric {m['id']} removed")
            continue
        if m.get("blocking") and not n.get("blocking"):
            problems.append(f"ratchet: metric {m['id']} no longer blocking")
        problems += [f"ratchet: metric {m['id']} {x}"
                     for x in _looser(m.get("threshold") or {}, n.get("threshold") or {})]
    new_slices = {(x["name"], x["metric"]): x for x in spec.get("slices") or []}
    for x in base_spec.get("slices") or []:
        n = new_slices.get((x["name"], x["metric"]))
        if n is None:
            problems.append(f"ratchet: slice {x['name']}/{x['metric']} removed")
            continue
        if x.get("blocking") and not n.get("blocking"):
            problems.append(f"ratchet: slice {x['name']}/{x['metric']} no longer blocking")
        problems += [f"ratchet: slice {x['name']}/{x['metric']} {y}" for y in _looser(x, n)]
    if base_spec.get("seeds") and sorted(spec.get("seeds") or []) != sorted(base_spec["seeds"]):
        problems.append(f"ratchet: seeds {base_spec['seeds']} -> {spec.get('seeds')}")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, mid = sl["name"], sl["metric"]
        sid = f"slice:{name}/{mid}"
        a, b = per_item(pr, mid, slice_name=name), per_item(base, mid, slice_name=name)
        verdict, note = "ok", ""
        val = round(sum(a.values()) / len(a), 4) if a else None
        if val is None:
            verdict = "missing"                       # an empty slice is not a passing slice
        elif "min" in sl and val < sl["min"]:
            verdict = "fail"
        keys = sorted(set(a) & set(b))
        if sl.get("no_significant_drop") and keys:
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        th = {k: sl[k] for k in ("min", "no_significant_drop") if k in sl}
        lines.append(f"  {sid:<34} {val!s:<8} {json.dumps(th):<38} {note:<28} {label} (n_items={len(a)})")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
