"""MJCF scene builder: free payload box, rigid canopy, slack-capable spatial-tendon lines,
ground + compliant landing pad, IMU site, RealSense-like cameras, LEDs and ArUco markers.

Built-in fluid forces are disabled (density=viscosity=0); aerodynamics are applied explicitly by
chutesim.aero so drag is never counted twice.
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from .config import REPO_ROOT
from .geometry import Geometry
from .payload import anchors_m, mass_properties


@lru_cache(maxsize=64)
def marker_bits(dictionary: str, marker_id: int) -> np.ndarray:
    import cv2
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dictionary))
    img = cv2.aruco.generateImageMarker(d, marker_id, 6)  # 4x4 bits + 1-cell border -> 6x6
    return (img < 128)  # True = black cell


def marker_layout(cfg: dict) -> list[dict]:
    """ArUco markers fixed to the payload, from cfg payload.markers (each: id, center_m, right, up,
    size_m; normal = right x up). Payload V1 has none (no face large enough)."""
    out = []
    for mk in cfg["payload"].get("markers", []):
        r, u = np.asarray(mk["right"], float), np.asarray(mk["up"], float)
        out.append({"id": int(mk["id"]), "center": np.asarray(mk["center_m"], float), "right": r, "up": u,
                    "normal": np.cross(r, u), "size": float(mk["size_m"])})
    return out


def marker_corners_box(m: dict) -> np.ndarray:
    """ArUco corner order (TL, TR, BR, BL) in box frame."""
    s = m["size"] / 2
    c, r, u = m["center"], m["right"], m["up"]
    return np.array([c - r * s + u * s, c + r * s + u * s, c + r * s - u * s, c - r * s - u * s])


def led_layout(cfg: dict) -> list[dict]:
    """LED diffuser windows on the payload (centre, outward normal, size), payload frame."""
    return [{"center": np.asarray(w["center_m"], float), "normal": np.asarray(w["normal"], float),
             "size": np.asarray(w["size_m"], float)} for w in cfg["payload"]["led_windows"]]


def _fmt(v) -> str:
    return " ".join(f"{float(x):.9g}" for x in np.ravel(v))


def look_at_xyaxes(pos, target):
    f = np.asarray(target, float) - np.asarray(pos, float)
    f /= np.linalg.norm(f)
    right = np.cross(f, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    y = np.cross(-f, right)
    return right, y, f


def camera_poses(cfg: dict, pos=None, target=None) -> dict:
    """World poses of the colour, depth (left IR) and right IR imagers (MuJoCo convention)."""
    cc = cfg["camera"]
    pos = np.asarray(cc["position_m"] if pos is None else pos, float)
    target = np.asarray(cc["look_at_m"] if target is None else target, float)
    right, y, f = look_at_xyaxes(pos, target)
    d2c = np.asarray(cc["depth_to_color_m"], float)
    depth_pos = pos - right * d2c[0]
    rir_pos = depth_pos + right * cc["depth"]["baseline_m"]
    return {"right": right, "up": y, "forward": f, "color": pos, "depth": depth_pos, "rir": rir_pos}


def canopy_mesh(outline: np.ndarray, dome_h: float, thick: float = 0.0008):
    """Thin domed shell (closed prism) from a star-shaped outline. Returns vertices, faces."""
    n = len(outline)
    r = np.linalg.norm(outline, axis=1)
    rmax = r.max()
    z_top = dome_h * (1 - (r / rmax) ** 2)
    top = np.column_stack([outline, z_top + thick])
    bot = np.column_stack([outline, z_top])
    verts = np.vstack([[0, 0, dome_h + thick], [0, 0, dome_h], top, bot])
    ct, cb, t0, b0 = 0, 1, 2, 2 + n
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.append([ct, t0 + i, t0 + j])
        faces.append([cb, b0 + j, b0 + i])
        faces.append([t0 + i, b0 + i, b0 + j])
        faces.append([t0 + i, b0 + j, t0 + j])
    return verts, np.array(faces)


def build_mjcf(geom: Geometry, cfg: dict, line_lengths: np.ndarray, payload_pos, payload_quat,
               canopy_pos, canopy_quat, dome_h: float = 0.02) -> str:
    ph, pc, cc, cam, ct = cfg["physics"], cfg["payload"], cfg["canopy"], cfg["camera"], cfg["contact"]
    mp = mass_properties(cfg)
    m = mp["mass"]
    I = mp["I_com"]
    full_I = [I[0, 0], I[1, 1], I[2, 2], I[0, 1], I[0, 2], I[1, 2]]
    mc = cc["mass_kg"]
    Rc = geom.R_eq
    verts, faces = canopy_mesh(geom.outline, dome_h)

    # payload anchor sites (eyelet hole centres from CAD) and matching canopy attachment sites
    n_lines = cc["n_lines"]
    anchors = anchors_m(cfg)
    psites, csites = [], []
    for i in range(n_lines):
        psites.append(f'<site name="pa{i}" pos="{_fmt(anchors[i])}" size="0.003" rgba="1 0 0 1"/>')
        ap = geom.attach_points[i]
        csites.append(f'<site name="ca{i}" pos="{_fmt([ap[0], ap[1], 0.0])}" size="0.002"/>')

    rpy = np.radians(pc["imu_mount_rpy_deg"])
    imu_quat = _rpy_to_quat(*rpy)

    # markers: white plate + merged black runs
    mgeoms = []
    for mm in marker_layout(cfg):
        bits = marker_bits(pc["marker_dictionary"], mm["id"])
        s = mm["size"]
        c = s / 6
        R = np.column_stack([mm["right"], mm["up"], mm["normal"]])
        q = _mat_to_quat(R)
        plate = mm["center"] + mm["normal"] * 0.0003
        mgeoms.append(f'<geom type="box" size="{_fmt([s/2, s/2, 0.0003])}" pos="{_fmt(plate)}" quat="{_fmt(q)}" '
                      f'material="white" contype="0" conaffinity="0" group="1" mass="0"/>')
        for i in range(6):
            j = 0
            while j < 6:
                if bits[i, j]:
                    j0 = j
                    while j < 6 and bits[i, j]:
                        j += 1
                    w = (j - j0) * c
                    xr = -s / 2 + j0 * c + w / 2
                    yu = s / 2 - (i + 0.5) * c
                    p = mm["center"] + mm["right"] * xr + mm["up"] * yu + mm["normal"] * 0.0008
                    mgeoms.append(f'<geom type="box" size="{_fmt([w/2, c/2, 0.0003])}" pos="{_fmt(p)}" '
                                  f'quat="{_fmt(q)}" material="black" contype="0" conaffinity="0" group="1" mass="0"/>')
                else:
                    j += 1
    leds = []
    for i, w in enumerate(led_layout(cfg)):
        n = w["normal"]
        R = np.column_stack(_frame_from_normal(n))
        leds.append(f'<geom name="led{i}" type="box" size="{_fmt([w["size"][0] / 2, w["size"][1] / 2, 0.0006])}" '
                    f'pos="{_fmt(w["center"] + n * 0.0006)}" quat="{_fmt(_mat_to_quat(R))}" material="led" '
                    f'contype="0" conaffinity="0" group="1" mass="0"/>')
    # visual meshes (CAD, assembly frame) and convex collision primitives
    adir = REPO_ROOT / pc["assets_dir"]
    mesh_assets, vis = [], []
    for k, vm in enumerate(pc["visual_meshes"]):
        mesh_assets.append(f'<mesh name="pl{k}" file="{adir / vm["file"]}" scale="{pc["mesh_scale"]} {pc["mesh_scale"]} {pc["mesh_scale"]}"/>')
        c = vm["rgb"]
        vis.append(f'<geom name="payload_vis{k}" type="mesh" mesh="pl{k}" rgba="{c[0]} {c[1]} {c[2]} 1" '
                   f'contype="0" conaffinity="0" group="1" mass="0"/>')
    cols = []
    for k, cg in enumerate(pc["collision"]):
        common = (f'contype="1" conaffinity="1" solref="{_fmt(ct["pad_solref"])}" solimp="{_fmt(ct["pad_solimp"])}" '
                  f'friction="{_fmt(ct["friction"])}" mass="0" rgba="0 0 0 0" group="3"')
        if cg["type"] == "box":
            cols.append(f'<geom name="pcol{k}" type="box" size="{_fmt(cg["half_m"])}" pos="{_fmt(cg["center_m"])}" {common}/>')
        else:
            cols.append(f'<geom name="pcol{k}" type="cylinder" size="{cg["radius_m"]} {cg["half_len_m"]}" '
                        f'pos="{_fmt(cg["center_m"])}" {common}/>')

    tendons = []
    for i in range(n_lines):
        tendons.append(f'<spatial name="line{i}" limited="true" range="0 {line_lengths[i]:.6f}" '
                       f'solreflimit="0.004 1" width="0.0007" rgba="0.9 0.9 0.9 1">'
                       f'<site site="pa{i}"/><site site="ca{i}"/></spatial>')

    poses = camera_poses(cfg)
    right, up = poses["right"], poses["up"]
    # MuJoCo: square pixels, principal point at the image centre -> cx = (w-1)/2, cy = (h-1)/2 in OpenCV terms
    fovy_c = math.degrees(2 * math.atan(cam["color"]["height"] / 2 / cam["color"]["fy"]))
    fovy_d = math.degrees(2 * math.atan(cam["depth"]["height"] / 2 / cam["depth"]["fy"]))
    xy = _fmt(np.r_[right, up])
    pad = ct["pad_size_m"]
    off_w = max(cam["color"]["width"], cam["depth"]["width"])
    off_h = max(cam["color"]["height"], cam["depth"]["height"])

    return f"""<mujoco model="parachute_drop">
  <compiler angle="radian" autolimits="true"/>
  <option timestep="{ph['timestep']}" integrator="{ph['integrator']}" gravity="0 0 {-ph['g']}" density="0" viscosity="0"/>
  <visual>
    <global offwidth="{off_w}" offheight="{off_h}"/>
    <quality shadowsize="2048"/>
    <map znear="0.01" zfar="20"/>
    <headlight ambient="0.35 0.35 0.35" diffuse="0.5 0.5 0.5" specular="0.05 0.05 0.05"/>
  </visual>
  <asset>
    <texture name="sky" type="skybox" builtin="gradient" rgb1="0.75 0.78 0.8" rgb2="0.55 0.57 0.6" width="64" height="64"/>
    <texture name="floor" type="2d" builtin="checker" rgb1="0.42 0.42 0.44" rgb2="0.38 0.38 0.4" width="256" height="256"/>
    <material name="floor" texture="floor" texrepeat="8 8"/>
    <material name="white" rgba="0.97 0.97 0.97 1" specular="0"/>
    <material name="black" rgba="0.03 0.03 0.03 1" specular="0"/>
    <material name="led" rgba="0.05 0.25 0.05 1" emission="0"/>
    <material name="canopy" rgba="0.2 0.45 0.9 0.85"/>
    <material name="pad" rgba="0.15 0.15 0.17 1"/>
    <mesh name="canopy" vertex="{_fmt(verts)}" face="{_fmt(faces)}"/>
    {''.join(mesh_assets)}
  </asset>
  <worldbody>
    <light pos="0 -1 4" dir="0 0.25 -1" diffuse="0.6 0.6 0.6" castshadow="false"/>
    <geom name="ground" type="plane" size="5 5 0.1" material="floor" contype="1" conaffinity="3"
          solref="{_fmt(ct['pad_solref'])}" solimp="{_fmt(ct['pad_solimp'])}"/>
    <geom name="pad" type="box" size="{_fmt([pad[0]/2, pad[1]/2, pad[2]/2])}" pos="0 0 {pad[2]/2}" material="pad"
          contype="1" conaffinity="3" solref="{_fmt(ct['pad_solref'])}" solimp="{_fmt(ct['pad_solimp'])}" friction="{_fmt(ct['friction'])}"/>
    <camera name="color" mode="fixed" pos="{_fmt(poses['color'])}" xyaxes="{xy}" fovy="{fovy_c:.6f}"/>
    <camera name="depth" mode="fixed" pos="{_fmt(poses['depth'])}" xyaxes="{xy}" fovy="{fovy_d:.6f}"/>
    <camera name="rir" mode="fixed" pos="{_fmt(poses['rir'])}" xyaxes="{xy}" fovy="{fovy_d:.6f}"/>
    <body name="payload" pos="{_fmt(payload_pos)}" quat="{_fmt(payload_quat)}">
      <freejoint name="payload_free"/>
      <inertial pos="{_fmt(mp['com'])}" mass="{m}" fullinertia="{_fmt(full_I)}"/>
      {''.join(vis)}
      {''.join(cols)}
      <site name="imu" pos="{_fmt(pc['imu_offset_m'])}" quat="{_fmt(imu_quat)}" size="0.003"/>
      {''.join(psites)}
      {''.join(mgeoms)}
      {''.join(leds)}
    </body>
    <body name="canopy" pos="{_fmt(canopy_pos)}" quat="{_fmt(canopy_quat)}">
      <freejoint name="canopy_free"/>
      <inertial pos="0 0 0" mass="{mc}" diaginertia="{mc*Rc**2/4:.9g} {mc*Rc**2/4:.9g} {mc*Rc**2/2:.9g}"/>
      <geom name="canopy_vis" type="mesh" mesh="canopy" material="canopy" contype="0" conaffinity="0" group="1" mass="0"/>
      <geom name="canopy_col" type="cylinder" size="{0.8*Rc:.6f} 0.002" contype="2" conaffinity="0" rgba="0 0 0 0" mass="0"/>
      {''.join(csites)}
    </body>
  </worldbody>
  <tendon>
    {''.join(tendons)}
  </tendon>
  <sensor>
    <accelerometer name="acc" site="imu"/>
    <gyro name="gyro" site="imu"/>
  </sensor>
</mujoco>"""


def _frame_from_normal(n):
    n = np.asarray(n, float)
    t = np.array([0, 0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0, 0])
    x = np.cross(t, n)
    x /= np.linalg.norm(x)
    return x, np.cross(n, x), n


def _rpy_to_quat(r, p, y):
    cr, sr, cp, sp, cy, sy = math.cos(r/2), math.sin(r/2), math.cos(p/2), math.sin(p/2), math.cos(y/2), math.sin(y/2)
    return np.array([cr*cp*cy + sr*sp*sy, sr*cp*cy - cr*sp*sy, cr*sp*cy + sr*cp*sy, cr*cp*sy - sr*sp*cy])


def _mat_to_quat(R):
    import mujoco
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, np.ascontiguousarray(R).ravel())
    return q
