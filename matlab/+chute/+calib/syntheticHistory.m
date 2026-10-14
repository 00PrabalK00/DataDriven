function [t, h, truth] = syntheticHistory(p, mismatch, noiseSd, seed, fs)
%SYNTHETICHISTORY Height-above-pad history after release, generated with a chosen (possibly
%mismatched) physics model, sampled at fs Hz with Gaussian measurement noise. Used only for
%calibration-infrastructure validation (L1), never as evidence about real parachutes.
% mismatch: 'none' | 'logistic_opening' | 'drag_exponent_1.8' | 'velocity_porosity' |
%           'line_elasticity' | 'bias_drift'
if nargin < 5, fs = 200; end
rng(seed, 'twister');
q = p; q.tmax = 5;
switch mismatch
    case 'none'
    case 'logistic_opening', q.opening = 'logistic';
    case 'drag_exponent_1.8', q.n = 1.8; q.K_o = p.K_o * 4^(0.2); q.K_i = p.K_i * 4^(0.2); % same K at ~4 m/s
    case {'velocity_porosity', 'line_elasticity'}
        % handled by a custom ODE below
    case 'bias_drift'
    otherwise, error('chute:mismatch', 'unknown mismatch %s', mismatch);
end
if any(strcmp(mismatch, {'velocity_porosity', 'line_elasticity'}))
    Kf = chute.ode.openingModel(struct('opening', 'exp', 'K_i', p.K_i, 'K_o', p.K_o, 'tau', p.tau));
    if strcmp(mismatch, 'velocity_porosity')
        Keff = @(t, v) Kf(t) .* (1 - 0.04 * max(abs(v) - 3, 0));       % porosity grows with speed
    else
        Keff = @(t, v) Kf(t) .* (1 + 0.08 * sin(2*pi*6*t) .* (t > p.tau)); % line stretch oscillation
    end
    rhs = @(t, y) [-y(2); p.g - 0.5*p.rho*(Keff(t, y(2)) + p.K_box)*abs(y(2))*y(2)/p.m];
    o = odeset('Events', @groundEvent, 'RelTol', 1e-9, 'AbsTol', 1e-11);
    sol = ode45(rhs, [0 5], [p.h0; p.v0], o);
    tc = sol.xe(1);
    t = (0:1/fs:tc)';
    Y = deval(sol, t); hh = Y(1,:)'; vv = Y(2,:)';
else
    s = chute.ode.simulateDrop(q);
    tc = s.t_contact;
    t = (0:1/fs:tc)';
    hh = interp1(s.t, s.h, t); vv = interp1(s.t, s.v, t);
end
if strcmp(mismatch, 'bias_drift')
    hh = hh - 0.5 * 0.08 * t.^2;    % unmodelled accelerometer-bias-like drift in the estimate
end
h = hh + noiseSd * randn(size(hh));
truth.v_contact = vv(end); truth.t_contact = tc; truth.mismatch = mismatch;
end

function [value, isterminal, direction] = groundEvent(~, y)
%GROUNDEVENT Stop when the box reaches the pad (height crosses zero downward).
value = y(1); isterminal = 1; direction = -1;
end
