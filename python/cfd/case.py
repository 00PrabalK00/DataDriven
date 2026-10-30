"""OpenFOAM case from an STL: blockMesh box + snappyHexMesh + simpleFoam (k-omega SST) + force objects.

Frame: freestream U = U (sin a, 0, cos a) (canopy axis +z, mouth facing -z); the inflow vector is rotated,
the mesh is not. Pitch axis -y: positive Cm increases alpha, so Cm_alpha < 0 = self-righting.
The canopy is meshed as a zero-thickness baffle by default (robust at coarse resolution; slits stay
open where the gap is resolved by the feature refinement); `solid=True` meshes the closed 1 mm shell.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from . import runner

REPO = Path(__file__).resolve().parents[2]
WORK = Path(os.environ.get("CFD_WORK", REPO / "results" / "cfd" / "cases"))
U_INF = 7.0
NU = 1.5e-5
RHO = 1.204


@dataclass
class MeshParams:
    """Mesh controls. level = surface refinement level relative to the base cell h0 = D / cells_per_D."""
    level: int = 5
    feature_extra: int = 1          # rim + slit edges refined to level + feature_extra
    cells_per_D: float = 2.0
    upstream_D: float = 8.0
    side_D: float = 8.0
    downstream_D: float = 15.0
    near_drop: int = 2              # near box at level - near_drop
    wake_drop: int = 3
    far_drop: int = 4
    cells_between_levels: int = 3


@dataclass
class SolverParams:
    n_iter: int = 1500
    avg_frac: float = 0.3
    turb_intensity: float = 0.01
    nut_ratio: float = 10.0
    potential_init: bool = True
    transient: bool = False         # pimpleFoam continuation from the steady solution
    t_transient: float = 0.6        # s of physical time (several shedding periods at St ~ 0.13)
    co_max: float = 2.0


def _vec(v) -> str:
    return "(" + " ".join(f"{float(x):.9g}" for x in v) + ")"


HEADER = """FoamFile
{{
    version     2.0;
    format      ascii;
    class       {cls};
    object      {obj};
}}
"""


def _w(path: Path, cls: str, obj: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEADER.format(cls=cls, obj=obj) + body)


def flow_dirs(alpha_deg: float):
    a = math.radians(alpha_deg)
    drag = np.array([math.sin(a), 0.0, math.cos(a)])
    lift = np.array([math.cos(a), 0.0, -math.sin(a)])
    pitch = np.array([0.0, -1.0, 0.0])
    return drag, lift, pitch


def write_case(case: Path, stl: Path, *, D: float, Aref: float, cofr, alpha_deg: float, n_procs: int,
               mesh: MeshParams, solver: SolverParams, sample: bool = False) -> dict:
    """Write all case dictionaries; returns meta (box, cell sizes)."""
    case = Path(case)
    if case.exists():
        shutil.rmtree(case)
    (case / "constant" / "triSurface").mkdir(parents=True)
    shutil.copy(stl, case / "constant" / "triSurface" / "canopy.stl")
    V = np.loadtxt([l for l in open(stl) if l.strip().startswith("vertex")], usecols=(1, 2, 3))
    lo, hi = V.min(0), V.max(0)
    c = 0.5 * (lo + hi)
    drag, lift, pitch = flow_dirs(alpha_deg)
    Uvec = U_INF * drag

    # --- blockMesh
    h0 = D / mesh.cells_per_D
    f = 0.1357 * h0  # shift so no flat surface coincides with cell faces/centres at levels 3-8
    xmin = np.array([c[0] - mesh.side_D * D + f, c[1] - mesh.side_D * D + f, c[2] - mesh.upstream_D * D + f])
    n = np.array([round(2 * mesh.side_D * D / h0), round(2 * mesh.side_D * D / h0),
                  round((mesh.upstream_D + mesh.downstream_D) * D / h0)], int)
    xmax = xmin + n * h0
    verts = [[xmin[0], xmin[1], xmin[2]], [xmax[0], xmin[1], xmin[2]], [xmax[0], xmax[1], xmin[2]],
             [xmin[0], xmax[1], xmin[2]], [xmin[0], xmin[1], xmax[2]], [xmax[0], xmin[1], xmax[2]],
             [xmax[0], xmax[1], xmax[2]], [xmin[0], xmax[1], xmax[2]]]
    _w(case / "system" / "blockMeshDict", "dictionary", "blockMeshDict", f"""
scale 1;
vertices ( {' '.join(_vec(v) for v in verts)} );
blocks ( hex (0 1 2 3 4 5 6 7) ({n[0]} {n[1]} {n[2]}) simpleGrading (1 1 1) );
boundary ( farfield {{ type patch; faces ( (0 3 2 1) (4 5 6 7) (0 1 5 4) (2 3 7 6) (1 2 6 5) (0 4 7 3) ); }} );
""")

    # --- features + snappy
    L = mesh.level
    _w(case / "system" / "surfaceFeatureExtractDict", "dictionary", "surfaceFeatureExtractDict", """
canopy.stl
{
    extractionMethod extractFromSurface;
    extractFromSurfaceCoeffs { includedAngle 60; }
    subsetFeatures { nonManifoldEdges yes; openEdges yes; }
    writeObj no;
}
""")
    ta = math.tan(math.radians(abs(alpha_deg)))
    sgn = 1 if alpha_deg >= 0 else -1

    def box(lat, up, down, name, lev):
        if lev < 1:
            return "", ""
        x0, x1 = c[0] - lat * D, c[0] + lat * D
        if sgn > 0:
            x1 += ta * down * D
        else:
            x0 -= ta * down * D
        g = f"    {name} {{ type searchableBox; min ({x0:.6g} {c[1]-lat*D:.6g} {c[2]-up*D:.6g}); max ({x1:.6g} {c[1]+lat*D:.6g} {c[2]+down*D:.6g}); }}\n"
        r = f"        {name} {{ mode inside; levels ((1e15 {lev})); }}\n"
        return g, r
    regs = [box(0.8, 0.6, 1.5, "nearBox", L - mesh.near_drop), box(1.5, 1.5, 6.0, "wakeBox", L - mesh.wake_drop),
            box(3.0, 3.0, 12.0, "farBox", L - mesh.far_drop)]
    geo = "".join(r[0] for r in regs)
    rr = "".join(r[1] for r in regs)
    loc = c + np.array([3.1 * D + 0.0123, 2.9 * D + 0.0071, -5.3 * D - 0.0057])
    solid = _is_closed(V)
    surf = (f"canopy {{ level ({L} {L}); patchInfo {{ type wall; }} }}" if solid else
            f"canopy {{ level ({L} {L}); faceZone canopy; faceType baffle; patchInfo {{ type wall; }} }}")
    _w(case / "system" / "snappyHexMeshDict", "dictionary", "snappyHexMeshDict", f"""
castellatedMesh true;
snap            true;
addLayers       false;
geometry
{{
    canopy.stl {{ type triSurfaceMesh; name canopy; }}
{geo}}}
castellatedMeshControls
{{
    maxLocalCells 4000000;
    maxGlobalCells 40000000;
    minRefinementCells 0;
    maxLoadUnbalance 0.10;
    nCellsBetweenLevels {mesh.cells_between_levels};
    features ( {{ file "canopy.eMesh"; level {L + mesh.feature_extra}; }} );
    refinementSurfaces {{ {surf} }}
    resolveFeatureAngle 30;
    refinementRegions
    {{
{rr}    }}
    locationInMesh {_vec(loc)};
    allowFreeStandingZoneFaces true;
}}
snapControls
{{
    nSmoothPatch 3;
    tolerance 2.0;
    nSolveIter 50;
    nRelaxIter 5;
    nFeatureSnapIter 10;
    implicitFeatureSnap false;
    explicitFeatureSnap true;
    multiRegionFeatureSnap false;
}}
addLayersControls
{{
    relativeSizes true; layers {{ }}; expansionRatio 1.2; finalLayerThickness 0.5; minThickness 0.1;
    nGrow 0; featureAngle 60; nRelaxIter 3; nSmoothSurfaceNormals 1; nSmoothNormals 3; nSmoothThickness 10;
    maxFaceThicknessRatio 0.5; maxThicknessToMedialRatio 0.3; minMedialAxisAngle 90; nBufferCellsNoExtrude 0;
    nLayerIter 50;
}}
meshQualityControls
{{
    maxNonOrtho 65; maxBoundarySkewness 20; maxInternalSkewness 4; maxConcave 80; minVol 1e-15;
    minTetQuality 1e-15; minArea -1; minTwist 0.02; minDeterminant 0.001; minFaceWeight 0.05;
    minVolRatio 0.01; minTriangleTwist -1; nSmoothScale 4; errorReduction 0.75;
    relaxed {{ maxNonOrtho 75; }}
}}
mergeTolerance 1e-6;
""")
    _w(case / "system" / "decomposeParDict", "dictionary", "decomposeParDict",
       _decomp_dict(n_procs))

    # --- fields (0.orig)
    k = 1.5 * (solver.turb_intensity * U_INF) ** 2
    om = k / (solver.nut_ratio * NU)
    bc_common = '    #includeEtc "caseDicts/setConstraintTypes"\n'
    _w(case / "0.orig" / "U", "volVectorField", "U", f"""
dimensions [0 1 -1 0 0 0 0];
internalField uniform {_vec(Uvec)};
boundaryField
{{
{bc_common}    farfield {{ type freestreamVelocity; freestreamValue uniform {_vec(Uvec)}; }}
    "canopy.*" {{ type noSlip; }}
}}
""")
    _w(case / "0.orig" / "p", "volScalarField", "p", f"""
dimensions [0 2 -2 0 0 0 0];
internalField uniform 0;
boundaryField
{{
{bc_common}    farfield {{ type freestreamPressure; freestreamValue uniform 0; }}
    "canopy.*" {{ type zeroGradient; }}
}}
""")
    for name, val, wall, dim in (("k", k, "kqRWallFunction", "[0 2 -2 0 0 0 0]"),
                                 ("omega", om, "omegaWallFunction", "[0 0 -1 0 0 0 0]")):
        _w(case / "0.orig" / name, "volScalarField", name, f"""
dimensions {dim};
internalField uniform {val:.6g};
boundaryField
{{
{bc_common}    farfield {{ type inletOutlet; inletValue uniform {val:.6g}; value uniform {val:.6g}; }}
    "canopy.*" {{ type {wall}; value uniform {val:.6g}; }}
}}
""")
    _w(case / "0.orig" / "nut", "volScalarField", "nut", f"""
dimensions [0 2 -1 0 0 0 0];
internalField uniform 0;
boundaryField
{{
{bc_common}    farfield {{ type calculated; value uniform 0; }}
    "canopy.*" {{ type nutkWallFunction; value uniform 0; }}
}}
""")

    # --- constant
    _w(case / "constant" / "transportProperties", "dictionary", "transportProperties",
       f"transportModel Newtonian;\nnu {NU:g};\n")
    _w(case / "constant" / "turbulenceProperties", "dictionary", "turbulenceProperties",
       "simulationType RAS;\nRAS { RASModel kOmegaSST; turbulence on; printCoeffs off; }\n")

    # --- system
    _write_controls(case, solver=solver, cofr=cofr, D=D, Aref=Aref, alpha_deg=alpha_deg, sample=sample,
                    center=c, transient=False)
    _w(case / "system" / "fvSchemes", "dictionary", "fvSchemes", """
ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; grad(U) cellLimited Gauss linear 1; grad(k) cellLimited Gauss linear 1; grad(omega) cellLimited Gauss linear 1; }
divSchemes
{
    default none;
    div(phi,U) bounded Gauss linearUpwind grad(U);
    div(phi,k) bounded Gauss upwind;
    div(phi,omega) bounded Gauss upwind;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
    div(div(phi,U)) Gauss linear;
}
laplacianSchemes { default Gauss linear limited corrected 0.5; }
interpolationSchemes { default linear; }
snGradSchemes { default limited corrected 0.5; }
wallDist { method meshWave; }
""")
    _w(case / "system" / "fvSolution", "dictionary", "fvSolution", """
solvers
{
    p { solver GAMG; smoother GaussSeidel; tolerance 1e-7; relTol 0.05; }
    Phi { $p; }
    "(U|k|omega)" { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.1; nSweeps 1; }
    "(U|k|omega)Final" { $U; relTol 0; }
    pFinal { $p; relTol 0; }
}
SIMPLE
{
    nNonOrthogonalCorrectors 0;
    consistent yes;
    residualControl { p 1e-5; U 1e-6; "(k|omega)" 1e-6; }
}
PIMPLE { nOuterCorrectors 2; nCorrectors 2; nNonOrthogonalCorrectors 0; }
potentialFlow { nNonOrthogonalCorrectors 5; }
relaxationFactors { equations { U 0.9; ".*" 0.5; } }
""")
    return {"box_min": xmin.tolist(), "box_max": xmax.tolist(), "base_cells": n.tolist(), "h0": h0,
            "h_surface": h0 / 2**L, "h_feature": h0 / 2 ** (L + mesh.feature_extra), "solid": solid,
            "U": Uvec.tolist(), "center": c.tolist()}


def _write_controls(case: Path, *, solver: SolverParams, cofr, D, Aref, alpha_deg, sample, center, transient):
    drag, lift, pitch = flow_dirs(alpha_deg)
    fo = f"""
    forces1
    {{
        type forces; libs (forces); writeControl timeStep; writeInterval 1;
        patches ("canopy.*"); rho rhoInf; rhoInf {RHO}; CofR {_vec(cofr)};
    }}
    forceCoeffs1
    {{
        type forceCoeffs; libs (forces); writeControl timeStep; writeInterval 1;
        patches ("canopy.*"); rho rhoInf; rhoInf {RHO}; CofR {_vec(cofr)};
        dragDir {_vec(drag)}; liftDir {_vec(lift)}; pitchAxis {_vec(pitch)};
        magUInf {U_INF}; lRef {D:.6g}; Aref {Aref:.6g};
    }}
    residuals {{ type solverInfo; libs (utilityFunctionObjects); fields (U p k omega); writeResidualFields no; }}
"""
    if sample:
        fo += f"""
    planes
    {{
        type surfaces; libs (sampling); writeControl writeTime; surfaceFormat raw; fields (U p);
        interpolationScheme cellPoint;
        surfaces
        {{
            midY {{ type cuttingPlane; planeType pointAndNormal;
                    pointAndNormalDict {{ point {_vec(center)}; normal (0 1 0); }} interpolate true; }}
        }}
    }}
    canopyP
    {{
        type surfaces; libs (sampling); writeControl writeTime; surfaceFormat vtk;
        formatOptions {{ vtk {{ format ascii; legacy true; }} }}
        fields (p); interpolationScheme cellPoint;
        surfaces {{ canopy {{ type patch; patches ("canopy.*"); interpolate false; }} }}
    }}
"""
    if transient:
        app = f"""application pimpleFoam;
startFrom latestTime; stopAt endTime; endTime {solver.n_iter + solver.t_transient:.6g};
deltaT 1e-4; adjustTimeStep yes; maxCo {solver.co_max}; maxDeltaT 0.01;
writeControl adjustable; writeInterval {solver.t_transient:.6g}; purgeWrite 1;
"""
    else:
        app = f"""application simpleFoam;
startFrom latestTime; stopAt endTime; endTime {solver.n_iter}; deltaT 1;
writeControl timeStep; writeInterval {max(solver.n_iter, 1)}; purgeWrite 1;
"""
    _w(case / "system" / "controlDict", "dictionary", "controlDict", app + f"""
writeFormat binary; writePrecision 8; writeCompression off; timeFormat general; timePrecision 8;
runTimeModifiable false;
functions
{{{fo}}}
""")


def _is_closed(V: np.ndarray) -> bool:
    """True when the STL is watertight (every edge shared by exactly two facets)."""
    P = np.round(V / 1e-9).astype(np.int64)
    _, idx = np.unique(P, axis=0, return_inverse=True)
    F = idx.reshape(-1, 3)
    e = np.sort(np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), 1)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    return bool(np.all(cnt == 2))


def allrun(n_procs: int, solver: SolverParams) -> str:
    """Bash script run inside the OpenFOAM environment."""
    par = n_procs > 1
    R = f"mpirun -np {n_procs} " if par else ""
    P = " -parallel" if par else ""
    s = f"""
t0=$SECONDS
st() {{ echo "$1 $((SECONDS-t0))" >> timings.txt; }}
rm -f timings.txt
blockMesh > log.blockMesh 2>&1 || exit 11; st blockMesh
surfaceFeatureExtract > log.surfaceFeatureExtract 2>&1 || exit 12; st features
"""
    if par:
        s += "decomposePar -force > log.decomposePar 2>&1 || exit 13; st decompose\n"
    s += f"{R}snappyHexMesh{P} -overwrite > log.snappyHexMesh 2>&1 || exit 14; st snappy\n"
    if par:
        s += "for d in processor*; do rm -rf $d/0; cp -r 0.orig $d/0; done\n"
    else:
        s += "rm -rf 0; cp -r 0.orig 0\n"
    s += f"{R}checkMesh{P} -constant > log.checkMesh 2>&1; st checkMesh\n"
    if solver.n_iter <= 0:            # mesh only (cell-count / meshing-time measurement)
        return s
    if solver.potential_init:
        s += f"{R}potentialFoam{P} -writephi > log.potentialFoam 2>&1 || exit 15; st potentialFoam\n"
    s += f"{R}simpleFoam{P} > log.simpleFoam 2>&1 || exit 16; st simpleFoam\n"
    return s


def transient_script(n_procs: int) -> str:
    R = f"mpirun -np {n_procs} " if n_procs > 1 else ""
    P = " -parallel" if n_procs > 1 else ""
    return f"t0=$SECONDS\n{R}pimpleFoam{P} > log.pimpleFoam 2>&1 || exit 17\necho \"pimpleFoam $((SECONDS-t0))\" >> timings.txt\n"


# ---------------------------------------------------------------------------------------- post-process
def read_dat(path: Path) -> tuple[list[str], np.ndarray]:
    """Read an OpenFOAM function-object .dat file (last '#' line = column names)."""
    names, rows = [], []
    for line in open(path):
        if line.startswith("#"):
            t = line[1:].replace("(", " ").replace(")", " ").split()
            if t and t[0] == "Time":
                names = t
            continue
        v = line.replace("(", " ").replace(")", " ").split()
        if v:
            rows.append([float(x) for x in v])
    return names, np.array(rows)


def _fo_file(case: Path, fo: str, fname: str) -> Path | None:
    c = sorted((case / "postProcessing" / fo).glob(f"*/{fname}"), key=lambda p: float(p.parent.name))
    return c if c else None


def _load_series(case: Path, fo: str, fname: str):
    files = _fo_file(case, fo, fname)
    if not files:
        return None, None
    names, data = None, []
    for f in files:
        n, d = read_dat(f)
        names = names or n
        if len(d):
            data.append(d)
    return names, np.vstack(data)


def parse_results(case: Path, *, alpha_deg: float, Aref: float, D: float, cofr, conf=None,
                  avg_frac: float = 0.3, t_start: float | None = None) -> dict:
    """Average forces/moments over the last avg_frac of the history (or t >= t_start)."""
    drag, lift, pitch = flow_dirs(alpha_deg)
    nf, F = _load_series(case, "forces1", "force.dat")
    nm, M = _load_series(case, "forces1", "moment.dat")
    if F is None:
        return {"ok": False, "error": "no force output"}
    t = F[:, 0]
    sel = t >= (t_start if t_start is not None else t[0] + (1 - avg_frac) * (t[-1] - t[0]))
    Ft = F[:, 1:4]
    Mt = M[:, 1:4]
    Fm, Mm = Ft[sel].mean(0), Mt[sel].mean(0)
    q = 0.5 * RHO * U_INF**2
    fd_hist = Ft @ drag
    out = {"ok": True, "n_iter": int(t[-1]) if t_start is None else None, "t_end": float(t[-1]),
           "force_N": Fm.tolist(), "moment_Nm": Mm.tolist(), "cofr_m": list(map(float, cofr)),
           "drag_N": float(Fm @ drag), "lift_N": float(Fm @ lift),
           "CdA_m2": float(Fm @ drag / q), "Cd": float(Fm @ drag / (q * Aref)),
           "Cl": float(Fm @ lift / (q * Aref)), "Cm": float(Mm @ pitch / (q * Aref * D)),
           "drag_std_rel": float(np.std(fd_hist[sel]) / max(abs(np.mean(fd_hist[sel])), 1e-12)),
           "drag_trend_rel": _trend(t[sel], fd_hist[sel]),
           "Aref_m2": Aref, "lRef_m": D, "pressure_drag_frac": None}
    if F.shape[1] >= 7:
        out["pressure_drag_frac"] = float((F[sel, 4:7].mean(0) @ drag) / out["drag_N"])
    if conf is not None:
        Mc = Mm + np.cross(np.asarray(cofr) - np.asarray(conf), Fm)
        out["moment_conf_Nm"] = Mc.tolist()
        out["Cm_conf"] = float(Mc @ pitch / (q * Aref * D))
    _, C = _load_series(case, "forceCoeffs1", "coefficient.dat")
    nc, _ = _load_series(case, "forceCoeffs1", "coefficient.dat")
    if C is not None and nc:
        idx = {n: i for i, n in enumerate(nc)}
        selc = C[:, 0] >= t[sel][0]
        for key in ("Cd", "Cl", "CmPitch"):
            if key in idx and idx[key] < C.shape[1]:   # column layout differs between OpenFOAM versions
                out[f"fo_{key}"] = float(C[selc, idx[key]].mean())
    out["converged"] = bool(out["drag_std_rel"] < 0.02 and abs(out["drag_trend_rel"]) < 0.02)
    return out


def _trend(t, y) -> float:
    """Relative drift of y over the averaging window (linear fit slope * window / mean)."""
    if len(t) < 3:
        return 0.0
    a = np.polyfit(t, y, 1)[0]
    return float(a * (t[-1] - t[0]) / max(abs(np.mean(y)), 1e-12))


def mesh_cells(case: Path) -> int | None:
    for log in ("log.checkMesh", "log.snappyHexMesh"):
        p = case / log
        if p.exists():
            txt = p.read_text(errors="ignore")
            m = re.findall(r"^\s*cells:\s+(\d+)", txt, re.M) or re.findall(r"cells:(\d+)", txt)
            if m:
                return int(m[-1])
    return None


def foam_build(case: Path) -> str | None:
    for log in ("log.simpleFoam", "log.blockMesh"):
        p = case / log
        if p.exists():
            m = re.search(r"Build\s*:\s*(\S+)\s+OPENFOAM=(\d+)(?:\s+patch=(\d+))?", p.read_text(errors="ignore"))
            if m:
                return f"v{m.group(2)} build {m.group(1)}" + (f" patch {m.group(3)}" if m.group(3) else "")
    return None


def timings(case: Path) -> dict:
    p = case / "timings.txt"
    if not p.exists():
        return {}
    d, prev = {}, 0
    for line in p.read_text().split("\n"):
        if line.strip():
            k, v = line.split()
            d[k] = int(v) - prev if k != "pimpleFoam" else int(v)
            prev = int(v) if k != "pimpleFoam" else prev
    return d


def cleanup(case: Path, keep_logs_to: Path | None = None) -> None:
    """Copy logs/postProcessing to keep_logs_to, then delete the case directory."""
    if keep_logs_to is not None:
        keep_logs_to.mkdir(parents=True, exist_ok=True)
        for p in case.glob("log.*"):
            shutil.copy(p, keep_logs_to / p.name)
        for name in ("timings.txt",):
            if (case / name).exists():
                shutil.copy(case / name, keep_logs_to / name)
        if (case / "postProcessing").exists():
            shutil.copytree(case / "postProcessing", keep_logs_to / "postProcessing", dirs_exist_ok=True)
    shutil.rmtree(case, ignore_errors=True)


# --------------------------------------------------------------------------------------- high level
def run_stl(stl: Path, *, name: str, D: float, Aref: float, cofr, alpha_deg: float = 0.0, n_procs: int = 8,
            mesh: MeshParams | None = None, solver: SolverParams | None = None, conf=None,
            sample: bool = False, keep: bool = False, log_dir: Path | None = None) -> dict:
    """Build + run one case from an STL; returns averaged forces and run metadata."""
    mesh = mesh or MeshParams()
    solver = solver or SolverParams()
    case = WORK / name
    meta = write_case(case, stl, D=D, Aref=Aref, cofr=cofr, alpha_deg=alpha_deg, n_procs=n_procs,
                      mesh=mesh, solver=solver, sample=sample)
    t0 = time.time()
    rc = runner.run_script(case, allrun(n_procs, solver), case / "log.Allrun")
    res = {"name": name, "rc": rc, "alpha_deg": alpha_deg, "n_procs": n_procs, **asdict(mesh),
           "n_iter_max": solver.n_iter, **{f"mesh_{k}": v for k, v in meta.items()}}
    if rc == 0:
        res.update(parse_results(case, alpha_deg=alpha_deg, Aref=Aref, D=D, cofr=cofr, conf=conf,
                                 avg_frac=solver.avg_frac))
        res["steady"] = {k: res.get(k) for k in ("Cd", "CdA_m2", "Cm", "drag_std_rel", "converged")}
        if solver.transient and not res.get("converged", False):
            t_steady = res["t_end"]
            _write_controls(case, solver=solver, cofr=cofr, D=D, Aref=Aref, alpha_deg=alpha_deg,
                            sample=sample, center=np.array(meta["center"]), transient=True)
            _fix_transient_schemes(case)
            rc2 = runner.run_script(case, transient_script(n_procs), case / "log.Allrun.transient")
            res["rc_transient"] = rc2
            if rc2 == 0:
                tr = parse_results(case, alpha_deg=alpha_deg, Aref=Aref, D=D, cofr=cofr, conf=conf,
                                   t_start=t_steady + 0.5 * solver.t_transient)
                res.update(tr)
                res["solver_used"] = "pimpleFoam"
    res.setdefault("solver_used", "simpleFoam")
    res["runtime_s"] = time.time() - t0
    res["timings_s"] = timings(case)
    res["cells"] = mesh_cells(case)
    res["foam_build"] = foam_build(case)
    res.update(runner.describe())
    if not keep:
        cleanup(case, keep_logs_to=log_dir)
    elif log_dir is not None:
        cleanup_copy = log_dir
        cleanup_copy.mkdir(parents=True, exist_ok=True)
        for p in case.glob("log.*"):
            shutil.copy(p, cleanup_copy / p.name)
    return res


def _fix_transient_schemes(case: Path) -> None:
    p = case / "system" / "fvSchemes"
    txt = p.read_text().replace("default steadyState;", "default backward;")
    txt = txt.replace("bounded Gauss", "Gauss")
    p.write_text(txt)
    # parallel: fields of the latest time are already in processor dirs; nothing else to change


def design_key(design, extra: dict | None = None) -> str:
    d = {"q": float(design.q), "slit_len": float(design.slit_len), "slit_r": float(design.slit_r),
         "radial": [float(v) for v in design.radial] if design.radial is not None else None, **(extra or {})}
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:10]


def _decomp_dict(n_procs: int) -> str:
    """scotch by default; CFD_DECOMP=hierarchical for OpenFOAM builds without scotch (e.g. Ubuntu's v1912)."""
    import os
    n = max(n_procs, 1)
    if os.environ.get("CFD_DECOMP", "scotch") == "hierarchical":
        # n = a*b*c with a, b, c as balanced as possible (z = flow axis gets the largest factor)
        best = (1, 1, n)
        for a in range(1, n + 1):
            for b in range(1, n // a + 1):
                if a * b * (n // (a * b)) == n and max(a, b, n // (a * b)) < max(best):
                    best = (a, b, n // (a * b))
        a, b, c = sorted(best)
        return (f"numberOfSubdomains {n};\nmethod hierarchical;\n"
                f"coeffs {{ n ({a} {b} {c}); order xyz; }}\nhierarchicalCoeffs {{ n ({a} {b} {c}); order xyz; }}\n")
    return f"numberOfSubdomains {n};\nmethod scotch;\n"


def run_case(design, alpha_deg: float, n_procs: int = 8, level: int = 5, *, solver: SolverParams | None = None,
             mesh: MeshParams | None = None, cfg: dict | None = None, sample: bool = False,
             keep: bool = False, log_dir: Path | None = None, ff_kwargs: dict | None = None) -> dict:
    """Form-find the design, mesh and solve at alpha; returns Cd, Cl, Cm, CdA, forces, moments, cells, runtime."""
    from .formfind import write_canopy_stl
    from .shapes import get_shape
    c = get_shape(design, cfg, **(ff_kwargs or {}))
    key = design_key(design)
    stl = WORK / f"stl_{key}_a{alpha_deg:g}_L{level}.stl"
    stl.parent.mkdir(parents=True, exist_ok=True)
    write_canopy_stl(c, stl, solid=False)
    R_eq = math.sqrt(0.025 / math.pi)
    D, Aref = 2 * R_eq, 0.025
    mesh = mesh or MeshParams(level=level)
    mesh.level = level
    name = f"canopy_{key}_a{alpha_deg:g}_L{level}"
    res = run_stl(stl, name=name, D=D, Aref=Aref, cofr=c.centroid(), alpha_deg=alpha_deg, n_procs=n_procs,
                  mesh=mesh, solver=solver, conf=c.anchors.mean(0), sample=sample, keep=keep, log_dir=log_dir)
    s = c.summary()
    res.update({"design_key": key, "q": design.q, "slit_len": design.slit_len, "slit_r": design.slit_r,
                "projected_area_m2": s["projected_area_m2"], "porosity_proj": s["porosity_proj"],
                "slit_open_area_proj_m2": s["slit_open_area_proj_m2"], "height_m": s["height_m"],
                "CdA_proj_ratio": res.get("CdA_m2", float("nan")) / s["projected_area_m2"]})
    stl.unlink(missing_ok=True)
    return res
