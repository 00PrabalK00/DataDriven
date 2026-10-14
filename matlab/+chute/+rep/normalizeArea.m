function r = normalizeArea(r)
%NORMALIZEAREA Scale radial samples so the polar polygon has area pi (i.e. A0 when r is in R_eq units).
n = size(r,2); dth = 2*pi/n;
A = 0.5 * sin(dth) * sum(r .* circshift(r, -1, 2), 2);
r = r .* sqrt(pi ./ A);
end
