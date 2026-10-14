"""Per-frame perception: LED state, ArUco PnP box pose, depth-based axial range, colour-blob fallback.

Output measurements are timestamped in the host (camera) clock.
- "pnp": box-centre position (world) + orientation, covariance anisotropic (weak along the optical axis)
- "depth": scalar range of the box centre along the colour optical axis, at the DEPTH frame's timestamp
- "fallback": visible-surface centroid + depth, corrected toward the box centre by half the box depth
  along the viewing ray; isotropic, inflated covariance; no orientation
"""
from __future__ import annotations

import cv2
import numpy as np

from .geometry3d import K_matrix, align_depth_to_color


class Detector:
    def __init__(self, bundle, cfg_pipe: dict):
        self.b = bundle
        self.cp = cfg_pipe
        rig = bundle.meta["rig"]
        self.rig = rig
        d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, rig["marker_dictionary"]))
        params = cv2.aruco.DetectorParameters()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self.det = cv2.aruco.ArucoDetector(d, params)
        self.markers = {m["id"]: m for m in rig["markers"]}
        self.K = K_matrix(bundle.calib["color"])
        self.dist = np.asarray(bundle.calib["color"]["dist"], float)
        self.R_wc = np.asarray(bundle.calib["T_world_color"]["R"])
        self.t_wc = np.asarray(bundle.calib["T_world_color"]["t"])
        lo, hi = np.asarray(rig["extent_min_m"]), np.asarray(rig["extent_max_m"])
        self.half = (hi - lo) / 2          # half extents of the payload bounding box
        self.box_center = (hi + lo) / 2    # bounding-box centre in the payload frame
        self.fps = bundle.calib["stream"]["color_fps"]

    # ---------------- LED ----------------
    def led_state(self, bgr) -> bool:
        lo = np.array([0, self.cp["led_green_min"], 0], np.uint8)
        hi = np.array([self.cp["led_other_max"], 255, self.cp["led_other_max"]], np.uint8)
        return cv2.countNonZero(cv2.inRange(bgr, lo, hi)) >= self.cp["led_min_pixels"]

    # ---------------- markers ----------------
    def pnp(self, bgr):
        if not self.markers:          # payload without fiducials: nothing to detect
            return None
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = self.det.detectMarkers(gray)
        if ids is None:
            return None
        obj, img, used = [], [], []
        for c, i in zip(corners, ids.ravel()):
            m = self.markers.get(int(i))
            if m is None:
                continue
            obj.append(np.asarray(m["corners_box_m"]))
            img.append(c.reshape(4, 2))
            used.append(int(i))
        if not used:
            return None
        obj = np.vstack(obj).astype(np.float64)
        img = np.vstack(img).astype(np.float64)
        normals = {tuple(np.round(self.markers[i]["normal_box_m"], 6)) for i in used}
        if len(normals) == 1:
            # coplanar (single face): IPPE gives the two ambiguous solutions; choose by reprojection
            # error, and when that cannot separate them, by the protocol prior that the box hangs upright
            n_ok, rvecs, tvecs, errs = cv2.solvePnPGeneric(obj, img, self.K, self.dist, flags=cv2.SOLVEPNP_IPPE)
            if n_ok == 0:
                return None
            cands = []
            for rv, tv, e in zip(rvecs, tvecs, np.ravel(errs)):
                R_cb, _ = cv2.Rodrigues(rv)
                tilt = float(np.degrees(np.arccos(np.clip((self.R_wc @ R_cb)[2, 2], -1, 1))))
                cands.append((float(e), tilt, rv, tv))
            cands.sort(key=lambda c: c[0])
            if len(cands) > 1 and cands[1][0] < 1.5 * cands[0][0] + 0.3:
                cands = sorted(cands[:2], key=lambda c: c[1])
            _, _, rvec, tvec = cands[0]
        else:
            ok, rvec, tvec = cv2.solvePnP(obj, img, self.K, self.dist, flags=cv2.SOLVEPNP_SQPNP)
            if not ok:
                return None
            rvec, tvec = cv2.solvePnPRefineLM(obj, img, self.K, self.dist, rvec, tvec)
        proj, _ = cv2.projectPoints(obj, rvec, tvec, self.K, self.dist)
        err = float(np.sqrt(np.mean(np.sum((proj.reshape(-1, 2) - img) ** 2, axis=1))))
        if err > 3.0:
            return None
        R_cb, _ = cv2.Rodrigues(rvec)
        # well-determined anchor: centroid of the detected markers' centres (on the face plane)
        anchor_box = np.mean([self.markers[i]["center_box_m"] for i in used], axis=0)
        return {"R_cb": R_cb, "t_cb": tvec.ravel(), "ids": used, "reproj_px": err, "coplanar": len(normals) == 1,
                "anchor_box": anchor_box, "anchor_cam": R_cb @ anchor_box + tvec.ravel()}

    def face_polygon(self, pose, marker_ids):
        """Projected outlines of the box faces carrying the detected markers (colour pixels)."""
        polys = []
        faces = {}
        for i in marker_ids:
            n = tuple(np.round(self.markers[i]["normal_box_m"], 6))
            faces[n] = np.asarray(self.markers[i]["normal_box_m"])
        for n in faces.values():
            up = np.array([0, 0, 1.0])
            right = np.cross(up, n)
            hw = abs(right @ self.half)
            c = n * abs(n @ self.half)
            # shrink by 15% to stay off the silhouette edges (flying pixels / alignment gaps)
            pts = np.array([c + s1 * 0.85 * hw * right + s2 * 0.85 * self.half[2] * up
                            for s1, s2 in ((-1, 1), (1, 1), (1, -1), (-1, -1))])
            pc = (pose["R_cb"] @ pts.T).T + pose["t_cb"]
            if np.any(pc[:, 2] <= 0):
                continue
            uv = (self.K @ pc.T).T
            polys.append((uv[:, :2] / uv[:, 2:3], c))
        return polys

    def depth_axial(self, pose, marker_ids, depth_u16):
        polys = self.face_polygon(pose, marker_ids)
        if not polys:
            return None
        ci = self.b.calib["color"]
        allpts = np.vstack([p for p, _ in polys])
        x0, y0 = np.floor(allpts.min(0)).astype(int) - 4
        x1, y1 = np.ceil(allpts.max(0)).astype(int) + 4
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, ci["width"]), min(y1, ci["height"])
        if x1 <= x0 or y1 <= y0:
            return None
        aligned = align_depth_to_color(depth_u16, self.b.calib, roi=(x0, y0, x1, y1))
        best = None
        for poly, c_face in polys:
            mask = np.zeros(aligned.shape, np.uint8)
            cv2.fillConvexPoly(mask, np.round(poly).astype(np.int32), 1)
            vals = aligned[(mask > 0) & (aligned > 0)]
            if len(vals) < 20:
                continue
            zf = float(np.median(vals))
            # face centre -> box centre along the optical axis using the PnP orientation
            zc = zf + float((pose["R_cb"] @ (-c_face))[2])
            if best is None or len(vals) > best[1]:
                best = (zc, len(vals))
        return best

    # ---------------- fallback ----------------
    def blob(self, bgr, depth_u16):
        lo, hi = np.array(self.cp["box_hsv_lo"]), np.array(self.cp["box_hsv_hi"])
        # coarse pass at 1/4 resolution to find the candidate region, then full resolution on the crop
        small = cv2.inRange(cv2.cvtColor(bgr[::4, ::4], cv2.COLOR_BGR2HSV), lo, hi)
        if cv2.countNonZero(small) == 0:
            return None
        sy, sx = np.nonzero(small)
        H, W = bgr.shape[:2]
        ox, oy = max(int(sx.min()) * 4 - 12, 0), max(int(sy.min()) * 4 - 12, 0)
        ex, ey = min(int(sx.max()) * 4 + 16, W), min(int(sy.max()) * 4 + 16, H)
        m = np.zeros((H, W), np.uint8)
        m[oy:ey, ox:ex] = cv2.inRange(cv2.cvtColor(bgr[oy:ey, ox:ex], cv2.COLOR_BGR2HSV), lo, hi)
        n, lab, stats, cent = cv2.connectedComponentsWithStats(m)
        if n <= 1:
            return None
        k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        # merge nearby colour components (the lid / LEDs split the payload's visible colour)
        near = [j for j in range(1, n) if np.linalg.norm(cent[j] - cent[k]) < 40]
        sel = np.isin(lab, near)
        area = int(sel.sum())
        if area < self.cp["fallback_min_pixels"] or depth_u16 is None:
            return None
        ys, xs = np.nonzero(sel)
        x, y, w, h = xs.min(), ys.min(), xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
        aligned = align_depth_to_color(depth_u16, self.b.calib, roi=(max(x - 4, 0), max(y - 4, 0), x + w + 4, y + h + 4))
        msk = cv2.dilate(sel.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        vals = aligned[msk & (aligned > 0)]
        if len(vals) < 10:
            return None
        # thin object: many pixels in the mask see the background; take the NEAREST well-populated
        # depth cluster (2 cm bins) rather than the median
        bins = np.arange(vals.min(), vals.max() + 0.04, 0.02)
        cnt, edges = np.histogram(vals, bins=bins) if len(bins) > 1 else (np.array([len(vals)]), np.array([vals.min(), vals.min() + 0.02]))
        jb = int(np.nonzero(cnt >= max(5, 0.3 * cnt.max()))[0][0])
        zc = 0.5 * (edges[jb] + edges[jb + 1])
        Z = float(np.median(vals[np.abs(vals - zc) < 0.03]))
        cy_, cx_ = ys.mean(), xs.mean()
        cent_k = np.array([cx_, cy_])
        u, v = cent_k
        ray = np.linalg.solve(self.K, np.array([u, v, 1.0]))
        p_s = ray * Z
        # geometric correction: visible surface -> bounding-box centre (half the depth along the ray,
        # assuming a face toward the camera), then -> payload frame origin assuming it hangs upright
        p_c = p_s + ray / np.linalg.norm(ray) * self.half[0]
        p_c = p_c - self.R_wc.T @ self.box_center
        return {"p_cam": p_c, "pixels": area}

    # ---------------- run over the bundle ----------------
    def run(self):
        b, ep = self.b, self.cp["ekf"]
        dts = b.depth_times
        meas, led = [], []
        stats = {"frames": 0, "pnp": 0, "depth": 0, "fallback": 0}
        for frame, t in b.rgb_times:
            bgr = b.read_rgb(frame)
            if bgr is None:
                continue
            stats["frames"] += 1
            led.append((t, self.led_state(bgr)))
            pose = self.pnp(bgr)
            # nearest depth frame (separate timestamp)
            dep, t_dep = None, None
            if len(dts):
                j = int(np.argmin(np.abs(dts[:, 1] - t)))
                if abs(dts[j, 1] - t) < 1.0 / self.fps:
                    t_dep = float(dts[j, 1])
            if pose is not None:
                stats["pnp"] += 1
                R_wb = self.R_wc @ pose["R_cb"]
                p_w = self.R_wc @ pose["t_cb"] + self.t_wc
                a_w = self.R_wc @ pose["anchor_cam"] + self.t_wc
                dist = float(np.linalg.norm(pose["t_cb"]))
                scale = (dist / 1.8) * (1.0 if len(pose["ids"]) > 1 else 1.5)
                S_c = np.diag([ep["pos_sd_pnp_lateral"] ** 2, ep["pos_sd_pnp_lateral"] ** 2, ep["pos_sd_pnp_axial"] ** 2]) * scale**2
                att_sd = np.radians(ep["att_sd_pnp_deg"]) * scale * (2.0 if pose["coplanar"] else 1.0)
                meas.append({"t": float(t), "type": "pnp", "p": p_w, "R": R_wb,
                             "anchor_w": a_w, "anchor_box": pose["anchor_box"],
                             "cov": self.R_wc @ S_c @ self.R_wc.T, "att_sd": att_sd, "ids": pose["ids"]})
                if t_dep is not None:
                    dep = b.read_depth(dts[j, 0])
                    r = self.depth_axial(pose, pose["ids"], dep)
                    if r is not None:
                        stats["depth"] += 1
                        meas.append({"t": t_dep, "type": "depth", "z_cam": r[0], "sd": ep["pos_sd_depth"]})
            elif t_dep is not None:
                dep = b.read_depth(dts[j, 0])
                fb = self.blob(bgr, dep)
                if fb is not None:
                    stats["fallback"] += 1
                    p_w = self.R_wc @ fb["p_cam"] + self.t_wc
                    meas.append({"t": float(t), "type": "fallback", "p": p_w,
                                 "cov": np.eye(3) * ep["pos_sd_fallback"] ** 2})
        meas.sort(key=lambda m: m["t"])
        return meas, np.array(led, dtype=float).reshape(-1, 2), stats
