function S = sobolIndices(f, lb, ub, N, seed)
%SOBOLINDICES First-order and total Sobol indices (Saltelli sampling, Jansen estimators) of a
%vectorized function f(X) over the box [lb, ub]. Use on a surrogate or a cheap environment.
if nargin < 5, seed = 0; end
rng(seed, 'twister');
d = numel(lb);
A = lb + rand(N, d) .* (ub - lb);
B = lb + rand(N, d) .* (ub - lb);
fA = f(A); fB = f(B);
% centre the outputs: the estimators below lose all precision when the mean (e.g. ~6.85 m/s) is large
% compared with the variation between designs
f0 = mean([fA; fB]);
fA = fA - f0; fB = fB - f0;
V = var([fA; fB]);
S1 = zeros(1,d); ST = zeros(1,d);
for i = 1:d
    ABi = A; ABi(:,i) = B(:,i);
    fABi = f(ABi) - f0;
    S1(i) = mean(fB .* (fABi - fA)) / V;
    ST(i) = 0.5 * mean((fA - fABi).^2) / V;
end
S.first = S1; S.total = ST; S.interaction = ST - S1; S.N = N;
end
