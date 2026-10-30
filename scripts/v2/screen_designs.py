"""Full-simulator screen of many designs (fills the server's idle tail; feeds the real-drop tier choice).

  python scripts/v2/screen_designs.py --n 1000 --scenarios 5 --out results/screen_v2 [--mass 0.095]

Latin-hypercube designs over (q, slit_len, slit_r), each scored on the same 5 search scenarios as the
benchmark through chutesim's Evaluator (remote drop server if CHUTESIM_REMOTE is set). Writes
screen.csv incrementally in batches (resumable) with score, status, mean measured speed, lateral speed.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--scenarios", type=int, default=5)
    ap.add_argument("--batch", type=int, default=100)
    ap.add_argument("--mass", type=float, default=None, help="override payload mass [kg] (sensitivity)")
    ap.add_argument("--designs", default=None, help="JSON list of {q, slit_len, slit_r} instead of LHS")
    ap.add_argument("--out", default="results/screen_v2")
    ap.add_argument("--fresh", action="store_true", help="use the fresh (held-out) scenario seeds instead of the search seeds")
    ap.add_argument("--tag", default=None)
    a = ap.parse_args()
    from chutesim.config import load_config
    from chutesim.evaluate import Evaluator
    from ddd import doe
    cfg = load_config(None)
    tag = "screen"
    if a.mass:
        cfg["payload"]["mass_kg"] = a.mass
        tag = f"screen_m{a.mass:.3f}"
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    if a.designs:
        D = [[d["q"], d["slit_len"], d["slit_r"]] for d in json.load(open(a.designs))]
    else:
        res = doe.lhs_designs(n=a.n, seed=7, baselines=(), cfg=cfg)
        D = res[0] if isinstance(res, tuple) else res
        D = [list(map(float, d)) for d in (D["designs"] if isinstance(D, dict) else D)]
    base = cfg["objective"]["fresh_seed_base" if a.fresh else "search_seed_base"]
    if a.tag:
        tag = a.tag
    seeds = list(range(base, base + a.scenarios))
    path = out / f"{tag}.csv"
    done = 0
    if path.exists():
        done = sum(1 for _ in open(path)) - 1
    ev = Evaluator(cfg, n_workers=4)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if done <= 0:
            w.writerow(["q", "slit_len", "slit_r", "score", "status", "mean_preimpact_vz", "mean_lateral_speed", "cache_hits", "simulated_drops"])
            done = 0
        for i in range(done, len(D), a.batch):
            for r in ev.evaluate(D[i:i + a.batch], seeds, tag=tag):
                o = r["objective"]
                w.writerow([*r["design"], o["score"], o["status"], o.get("mean_preimpact_vz"), o.get("mean_lateral_speed"),
                            r["cache_hits"], r["simulated_drops"]])
            f.flush()
            print(f"{min(i + a.batch, len(D))}/{len(D)} designs", flush=True)
    ev.close()


if __name__ == "__main__":
    main()
