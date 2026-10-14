function env = latentEnv(decoder, k, seeds, opts)
%LATENTENV Objective environment for search in a learned/linear shape space: x = [z (1..k), slit_len,
%slit_r]; decoder(z) -> r(theta) rows. Shapes failing validity get the marked infeasibility penalty
%from the simulator's geometry check (counted as requests, as in the main benchmark).
arguments
    decoder function_handle
    k (1,1) double
    seeds (1,:) double
    opts.tag (1,:) char = 'latent'
    opts.n_workers double = []
end
env = @(X) callLatent(X, decoder, k, seeds, opts);
end

function r = callLatent(X, decoder, k, seeds, opts)
R = decoder(X(:, 1:k));
[res, ~] = chute.bridge.evaluateRadial(R, X(:, k+1:k+2), seeds, tag=opts.tag, n_workers=opts.n_workers);
n = numel(res);
r.score = zeros(n,1); r.status = strings(n,1); r.drops = zeros(n,1); r.cacheHits = zeros(n,1); r.secondary = zeros(n,1);
for i = 1:n
    o = res{i}.objective;
    r.score(i) = o.score; r.status(i) = string(o.status);
    r.drops(i) = res{i}.simulated_drops; r.cacheHits(i) = res{i}.cache_hits;
    if isfield(o, 'mean_lateral_speed') && ~isempty(o.mean_lateral_speed), r.secondary(i) = o.mean_lateral_speed;
    else, r.secondary(i) = o.P_infeasible; end
end
end
