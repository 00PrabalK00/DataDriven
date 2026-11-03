"""Winners of the free-form benchmark: noise-free re-score of every feasible request of every run, keep diverse
candidates (fastest, and fastest with better stability), keep those that really inflate, write them for CFD."""
import glob, json, pickle, sys, warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
S = ROOT / "results/freeform/server"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
m = pickle.load(open(S / "analysis/free_model.pkl", "rb"))

def ff(w):
    from chutesim.config import load_config
    from chutesim.freeform import free_design
    from cfd.formfind import form_find
    c = form_find(free_design(w, "D6"), load_config(None)); i = c.info
    return float(i.get("flutter_amp_m", 0)) * 1e3, int(i["slack_lines"]), c.summary()["projected_area_m2"]

rows = []
for f in glob.glob(str(S / "bench/free_runs/*.json")):
    r = json.load(open(f))
    meth = Path(f).stem.split("_")[0]
    X, F = np.array(r["X"]), np.array(r["F"])
    for i in np.argsort(F)[:12]:
        if F[i] < 9:
            rows.append((meth, X[i]))
print(len(rows), "candidates")
X = np.array([x for _, x in rows])
ok = np.array([m.feasible(x) for x in X]); X = X[ok]; M = [r[0] for r, o in zip(rows, ok) if o]
v, c = m.predict(X)
order = list(np.argsort(v))
stable_order = [i for i in np.argsort(v) if c[i] < 1.5e-3]   # clearly better stability than the vents (+2.25)
cand = []
def add(i):
    if all(np.linalg.norm(X[i] - X[j]) > 0.8 for j in cand):
        cand.append(i)
for lst, k in ((order, 2 * N), (stable_order, 2 * N)):
    n0 = len(cand)
    for i in lst:
        if len(cand) - n0 >= k:
            break
        add(i)
with ProcessPoolExecutor(len(cand)) as ex:
    H = list(ex.map(ff, [X[i] for i in cand]))
good = [(i, h) for i, h in zip(cand, H) if h[0] <= 5 and h[1] == 0]
print(len(cand), "form-found,", len(good), "inflate stably")
fast = sorted(good, key=lambda t: v[t[0]])
stab = sorted([g for g in good if c[g[0]] < 1.5e-3], key=lambda t: v[t[0]])
pick = fast[:N - 2] + [g for g in stab if g not in fast[:N - 2]][:2]
pick = (pick + [g for g in fast if g not in pick])[:N]
D = []
for k, (i, h) in enumerate(pick):
    D.append({"name": f"win{k}", "free": X[i].tolist(), "sym": "D6", "method": M[i], "pred_speed": float(v[i]), "pred_Cm": float(c[i]), "flutter_mm": h[0], "proj_cm2": h[2] * 1e4})
    print(D[-1]["name"], M[i], f"speed {v[i]:.3f} Cm {c[i]*1e3:+.2f} flutter {h[0]:.2f}mm proj {h[2]*1e4:.1f}")
json.dump(D, open(ROOT / "results/freeform/designs_win.json", "w"), indent=1)
json.dump(D, open(S / "designs_win.json", "w"), indent=1)
