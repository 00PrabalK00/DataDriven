"""Smoke test: evaluator with pool + cache (scratch dirs given as argv)."""
import json, sys, time
from chutesim.config import load_config
from chutesim.evaluate import Evaluator

if __name__ == "__main__":
    work, cache = sys.argv[1], sys.argv[2]
    cfg = load_config()
    ev = Evaluator(cfg, work_root=work, cache_root=cache, n_workers=4)
    try:
        t = time.time(); r = ev.evaluate([(2, 0, 0.3), (6, 0.2, 0.4)], [1000, 1001]); print("wall", time.time() - t)
        for x in r:
            o = x["objective"]
            print(x["canonical"], o["status"], round(o["score"], 3), o.get("mean_preimpact_vz"), o["sensing_failures"], x["cache_hits"], x["simulated_drops"])
        t = time.time(); r = ev.evaluate([(2, 0, 0.6)], [1000, 1001]); print("wall2", time.time() - t, r[0]["cache_hits"], r[0]["objective"]["score"])
        print(json.dumps(ev.counters))
    finally:
        ev.close()
