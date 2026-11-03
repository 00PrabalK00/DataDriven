"""Refit the free-form surrogate on shape features (all stable designs) and save it for the search environment."""
import csv, pickle, sys, warnings
from pathlib import Path
import numpy as np
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from chutesim.config import load_config
from cfd.fitmodel import make_gp
from ddd.free import FEATURES, FreeDescentModel
S = ROOT / "results/freeform/server"
R = list(csv.DictReader(open(S / "analysis/free_table.csv")))
X = np.array([[float(r[f]) for f in FEATURES] for r in R])
cda, cma = np.array([float(r["CdA"]) for r in R]), np.array([float(r["Cm_alpha"]) for r in R])
clf = pickle.load(open(S / "inflate/inflate_clf.pkl", "rb"))
m = FreeDescentModel(make_gp(X.shape[1]).fit(X, cda), make_gp(X.shape[1]).fit(X, cma), load_config(None), clf=clf)
pickle.dump(m, open(S / "analysis/free_model.pkl", "wb"))
print(len(R), "designs; model saved")
