function [cal, val] = splitGeometries(designIds, fracCal, seed)
%SPLITGEOMETRIES Disjoint calibration / validation split by GEOMETRY (all drops of a geometry stay on
%one side), so validation never reuses fitting data.
u = unique(designIds(:));
rng(seed, 'twister');
u = u(randperm(numel(u)));
nc = round(fracCal * numel(u));
cal = ismember(designIds, u(1:nc));
val = ~cal;
end
