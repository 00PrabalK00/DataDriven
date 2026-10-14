import numpy as np
import pytest

from chutesim.geometry import Design, boundary_radius, build_geometry, canonicalize


@pytest.mark.parametrize("q", [2.0, 3.3, 5.0, 8.0])
@pytest.mark.parametrize("l,r", [(0.0, 0.3), (0.1, 0.4), (0.25, 0.65), (0.25, 0.25)])
def test_net_area_exact(cfg, q, l, r):
    g = build_geometry(Design(q, l, r), cfg)
    assert abs(g.area_net - cfg["canopy"]["A0_m2"]) < 1e-9


def test_net_area_with_slot_width(cfg):
    import copy
    c = copy.deepcopy(cfg)
    c["canopy"]["slit_width_m"] = 0.003
    g = build_geometry(Design(4, 0.2, 0.45), c)
    assert g.area_removed > 0
    assert abs(g.area_net - c["canopy"]["A0_m2"]) < 1e-9
    assert g.area_outline > c["canopy"]["A0_m2"]


def test_q2_is_circle(cfg):
    g = build_geometry(Design(2.0, 0.0, 0.45), cfg)
    rad = np.linalg.norm(g.outline, axis=1)
    assert rad.std() / rad.mean() < 1e-12
    assert abs(rad.mean() - g.R_eq) / g.R_eq < 1e-4


def test_zero_slit_canonical(cfg):
    a = canonicalize(Design(3, 0.0, 0.3), cfg)
    b = canonicalize(Design(3, 0.0, 0.6), cfg)
    assert a.as_tuple() == b.as_tuple()
    ga = build_geometry(Design(3, 0.0, 0.3), cfg)
    gb = build_geometry(Design(3, 0.0, 0.6), cfg)
    assert ga.polygon_hash() == gb.polygon_hash()


def test_nonzero_slit_not_merged(cfg):
    assert canonicalize(Design(3, 1e-6, 0.3), cfg).slit_r == 0.3


def test_infeasible_rejected(cfg):
    import copy
    c = copy.deepcopy(cfg)
    c["canopy"]["bounds"]["slit_r"] = [0.0, 2.0]
    c["canopy"]["bounds"]["slit_len"] = [0.0, 1.0]
    g = build_geometry(Design(4, 0.25, 0.9), c)       # reaches the edge
    assert not g.feasible and "slit_reaches_edge" in g.reasons
    g = build_geometry(Design(4, 0.25, 0.1), c)       # centre bridge too narrow
    assert not g.feasible and "center_bridge_too_narrow" in g.reasons
    c["canopy"]["slit_angle_offset_deg"] = 22.5       # slits aligned with attachment patches
    g = build_geometry(Design(4, 0.2, 0.75), c)
    assert not g.feasible and "slit_intersects_attachment_patch" in g.reasons
    g = build_geometry(Design(9, 0.1, 0.4), cfg)
    assert "q_out_of_bounds" in g.reasons


def test_boundary_radius_square(cfg):
    g = build_geometry(Design(8.0, 0, 0.45), cfg)
    assert boundary_radius(g.outline, np.pi / 4) > boundary_radius(g.outline, 0.0)


def test_radial_design_exact_area_and_validity(cfg):
    import math
    th = np.linspace(0, 2 * np.pi, 64, endpoint=False)
    r = 1 + 0.1 * np.cos(3 * th)
    g = build_geometry(Design(0, 0.1, 0.45, tuple(r)), cfg)
    assert abs(g.area_net - cfg["canopy"]["A0_m2"]) < 1e-9 and g.feasible, g.reasons
    spiky = 1 + 0.6 * (np.arange(64) % 2)
    assert "radial_shape_invalid" in build_geometry(Design(0, 0.1, 0.45, tuple(spiky)), cfg).reasons


def test_radial_cache_key_distinct(cfg):
    from chutesim.evaluate import cache_key
    th = np.linspace(0, 2 * np.pi, 64, endpoint=False)
    a = tuple(1 + 0.1 * np.cos(3 * th))
    b = tuple(np.array(a) + 1e-7)
    assert cache_key(Design(0, 0.1, 0.45, a), 1000, cfg, "prior-v1")[0] != cache_key(Design(0, 0.1, 0.45, b), 1000, cfg, "prior-v1")[0]
