function g = geometry(q, slitLen, slitR)
%GEOMETRY Canopy geometry, features and prior aero parameters for one design (single source of
%truth is python/chutesim/geometry.py + aeromap.py; this wraps it through the bridge).
g = chute.bridge.call('geometry_json', q, slitLen, slitR);
end
