function [lb, ub] = bounds()
%BOUNDS Design-variable bounds [q, slit_len/R_eq, slit_r/R_eq] from the config.
c = chute.bridge.config();
b = c.canopy.bounds;
lb = [b.q(1) b.slit_len(1) b.slit_r(1)];
ub = [b.q(2) b.slit_len(2) b.slit_r(2)];
end
