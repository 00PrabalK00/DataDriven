function [D, info] = lhsDesigns(n, seed, opts)
%LHSDESIGNS n space-filling feasible designs (maximin LHS with feasibility rejection) plus the two
%unslit baselines (circle q=2, rounded square q=4). Returns D ((n+2) x 3) and info.isBaseline.
arguments
    n (1,1) double = 16
    seed (1,1) double = 1
    opts.baselines (:,3) double = [2 0 0.45; 4 0 0.45]
    opts.oversample (1,1) double = 6
end
rng(seed, 'twister');
[lb, ub] = chute.doe.bounds();
U = lhsdesign(opts.oversample * n, 3, 'criterion', 'maximin', 'iterations', 50);
C = lb + U .* (ub - lb);
ok = chute.doe.isFeasible(C);
C = C(ok, :);
if size(C,1) < n, error('chute:doe', 'only %d feasible candidates', size(C,1)); end
% greedy maximin subset in normalized coordinates
Z = (C - lb) ./ (ub - lb);
sel = 1; 
while numel(sel) < n
    d = min(pdist2(Z, Z(sel,:)), [], 2);
    d(sel) = -inf;
    [~, k] = max(d); sel(end+1) = k; %#ok<AGROW>
end
D = [C(sel,:); opts.baselines];
info.isBaseline = [false(n,1); true(size(opts.baselines,1),1)];
info.discrepancy = chute.doe.centeredL2Discrepancy(Z(sel,:));
info.minDistance = min(pdist(Z(sel,:)));
info.seed = seed;
end
