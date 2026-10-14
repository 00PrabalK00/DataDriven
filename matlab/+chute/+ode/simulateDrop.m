function out = simulateDrop(p)
%SIMULATEDROP Vertical drop model, downward velocity v positive:
%   m dv/dt = m g - 1/2 rho (K(t) + K_box) v|v|^(n-1),  dh/dt = -v
%   K(t) = K_i + (K_o - K_i)(1 - exp(-t/tau))            (opening = 'exp', default)
% Integrated with ode45 until the box reaches the pad (event h = 0).
% p fields: m, g, rho, K_i, K_o, tau, K_box, h0, v0 [, n (drag exponent, default 2), opening,
% tmax, sampleTimes]. 'opening' = 'exp' | 'logistic' | 'linear' (mismatch studies).
if ~isfield(p, 'n'), p.n = 2; end
if ~isfield(p, 'opening'), p.opening = 'exp'; end
if ~isfield(p, 'tmax'), p.tmax = 10; end
Kfun = chute.ode.openingModel(p);
rhs = @(t, y) [-y(2); p.g - 0.5 * p.rho * (Kfun(t) + p.K_box) * abs(y(2))^(p.n-1) * y(2) / p.m];
opts = odeset('Events', @groundEvent, 'RelTol', 1e-9, 'AbsTol', 1e-11);
if isfield(p, 'sampleTimes') && ~isempty(p.sampleTimes)
    tspan = [0; p.sampleTimes(:)];
    tspan = unique(tspan);
else
    tspan = [0 p.tmax];
end
[t, y, te, ye] = ode45(rhs, tspan, [p.h0; p.v0], opts);
out.t = t; out.h = y(:,1); out.v = y(:,2);
if isempty(te)
    out.t_contact = NaN; out.v_contact = NaN;
else
    out.t_contact = te(1); out.v_contact = ye(1,2);
end
out.v_terminal_open = sqrt(2 * p.m * p.g / (p.rho * (p.K_o + p.K_box)));
end

function [value, isterminal, direction] = groundEvent(~, y)
%GROUNDEVENT Stop when the box reaches the pad (height crosses zero downward).
value = y(1); isterminal = 1; direction = -1;
end
