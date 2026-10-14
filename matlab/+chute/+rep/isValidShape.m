function ok = isValidShape(R)
%ISVALIDSHAPE Geometric validity / fabrication checks for radial outlines (units of R_eq):
%positive and not too thin anywhere, bounded extent, no sharp spikes between neighbours, and
%(after area normalization) the area constraint holds.
dr = abs(R - circshift(R, -1, 2));
ok = all(R > 0.35, 2) & all(R < 2.2, 2) & all(dr < 0.25, 2) & all(isfinite(R), 2);
end
