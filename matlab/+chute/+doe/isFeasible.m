function [ok, reasons] = isFeasible(X)
%ISFEASIBLE Fabrication/geometry feasibility of designs (rows of X) via the shared geometry code.
n = size(X,1); ok = false(n,1); reasons = cell(n,1);
for i = 1:n
    g = chute.geom.geometry(X(i,1), X(i,2), X(i,3));
    ok(i) = g.feasible; reasons{i} = g.reasons;
end
end
