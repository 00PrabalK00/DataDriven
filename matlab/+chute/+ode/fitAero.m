function fit = fitAero(t, h, p0, opts)
%FITAERO Constrained least-squares fit of identifiable aero parameters to a measured height history.
% Only the effective drag area K = C_D*A (and opening parameters) is fitted: C_D and A are not
% separately identifiable from a short drop. t: times since release, h: height of box bottom above
% the pad. p0: struct with fixed m, g, rho, K_box, h0, v0 and initial guesses K_i, K_o, tau.
arguments
    t (:,1) double
    h (:,1) double
    p0 struct
    opts.fit (1,:) cell = {'K_o', 'tau'}
    opts.lb (1,:) double = []
    opts.ub (1,:) double = []
end
names = opts.fit;
x0 = cellfun(@(n) p0.(n), names);
lb = opts.lb; ub = opts.ub;
if isempty(lb), lb = zeros(size(x0)) + 1e-6; end
if isempty(ub), ub = x0 * 20 + 1; end
p = p0; p.sampleTimes = t;
    function r = resid(x)
        q = p;
        for k = 1:numel(names), q.(names{k}) = x(k); end
        s = chute.ode.simulateDrop(q);
        hm = interp1(s.t, s.h, t, 'linear', NaN);
        hm(isnan(hm)) = 0;   % after model contact the model sits on the pad
        r = hm - h;
    end
o = optimoptions('lsqnonlin', 'Display', 'off', 'FunctionTolerance', 1e-12, 'StepTolerance', 1e-12);
[x, resnorm, residual, ~, ~, ~, J] = lsqnonlin(@resid, x0, lb, ub, o);
fit = struct();
for k = 1:numel(names), fit.(names{k}) = x(k); end
fit.names = names; fit.x = x; fit.rmse = sqrt(resnorm / numel(t)); fit.residual = residual;
dof = max(numel(t) - numel(x), 1);
s2 = resnorm / dof;
C = s2 * inv(full(J' * J)); %#ok<MINV>
fit.se = sqrt(max(diag(C), 0))';
fit.ci95 = [x - 1.96 * fit.se; x + 1.96 * fit.se];
fit.corr = C ./ (fit.se' * fit.se);
end
