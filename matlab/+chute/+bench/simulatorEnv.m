function env = simulatorEnv(seeds, opts)
%SIMULATORENV Objective environment: simulator + virtual sensors + shared estimation pipeline
%(evidence level L2: synthetic benchmark under assumed aerodynamics).
arguments
    seeds (1,:) double
    opts.tag (1,:) char = 'bench'
    opts.log_path (1,:) char = ''
    opts.n_workers double = []
end
env = @(X) callSim(X, seeds, opts);
end

function r = callSim(X, seeds, opts)
[res, ~] = chute.bridge.evaluate(X, seeds, tag=opts.tag, log_path=opts.log_path, n_workers=opts.n_workers);
n = numel(res);
r.score = zeros(n,1); r.status = strings(n,1); r.drops = zeros(n,1); r.cacheHits = zeros(n,1);
r.secondary = zeros(n,1); r.meanSpeed = nan(n,1);
for i = 1:n
    o = res{i}.objective;
    r.score(i) = o.score; r.status(i) = string(o.status);
    r.drops(i) = res{i}.simulated_drops; r.cacheHits(i) = res{i}.cache_hits;
    if isfield(o, 'mean_lateral_speed') && ~isempty(o.mean_lateral_speed)
        r.secondary(i) = o.mean_lateral_speed;
    else
        r.secondary(i) = o.P_infeasible;   % marked penalty, not a measurement
    end
    if isfield(o, 'mean_preimpact_vz') && ~isempty(o.mean_preimpact_vz), r.meanSpeed(i) = o.mean_preimpact_vz; end
end
end
