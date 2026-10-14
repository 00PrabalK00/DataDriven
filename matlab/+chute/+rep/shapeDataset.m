function [R, info] = shapeDataset(n, seed, nTheta)
%SHAPEDATASET Rich canopy outlines as area-normalized radial functions r(theta)/R_eq sampled at
%nTheta angles. Families: superellipses, Fourier-perturbed circles (symmetric and asymmetric),
%rounded polygons. All rescaled to the same area (A0) exactly for the polar polygon.
% These are GEOMETRY samples only: they carry no aerodynamic labels.
if nargin < 3, nTheta = 64; end
rng(seed, 'twister');
th = (0:nTheta-1)' * 2*pi / nTheta;
R = zeros(n, nTheta); fam = strings(n,1);
for i = 1:n
    u = rand;
    if u < 0.35
        q = 2 + 6*rand;
        r = (abs(cos(th)).^q + abs(sin(th)).^q).^(-1/q);
        fam(i) = "superellipse";
    elseif u < 0.75
        r = ones(nTheta,1);
        sym = rand < 0.5;
        for k = 2:8
            if sym && mod(k,4) ~= 0, continue; end
            r = r + (0.15/k) * randn * cos(k*th + 2*pi*rand);
        end
        fam(i) = "fourier";
    else
        m = randi([3 8]); rho = 0.15 + 0.5*rand;
        phi = mod(th + pi/m, 2*pi/m) - pi/m;
        r = cos(pi/m) ./ cos(phi);
        r = (1-rho) * r + rho;            % blend toward circle = rounding
        fam(i) = "rounded_polygon";
    end
    R(i,:) = chute.rep.normalizeArea(r(:)');
end
info.family = fam; info.valid = chute.rep.isValidShape(R); info.theta = th';
end
