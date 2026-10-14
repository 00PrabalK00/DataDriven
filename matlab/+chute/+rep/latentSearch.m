function T = latentSearch(R, P, A, V, opts)
%LATENTSEARCH Same search method and budget in different design representations:
%  param3 (q, slit len, slit r) | PCA latent | autoencoder latent | VAE latent  (+ slit len, slit r).
%Reports best score, valid-geometry rate and requests per representation (L2).
arguments
    R double            % training outlines (for latent bounds)
    P struct            % chute.rep.pcaStudy output
    A struct            % chute.rep.aeStudy output (nets for each k)
    V struct            % chute.rep.vaeStudy output
    opts.k (1,1) double = 4
    opts.budget (1,1) double = 50
    opts.nRuns (1,1) double = 3
    opts.nScenarios (1,1) double = 3
    opts.method (1,:) char = 'bo'
end
cfg = chute.bridge.config();
seeds = cfg.objective.search_seed_base + (0:opts.nScenarios-1);
[lb3, ub3] = chute.doe.bounds();
k = opts.k;
% PCA
pcaDec = @(Z) Z * P.coeff(:,1:k)' + P.mu;
Zp = (R - P.mu) * P.coeff(:,1:k);
% AE (decoder = layers after the code layer)
ia = find(A.k == k, 1); net = A.nets{ia};
aeEnc = encoderOf(net); aeDec = decoderOf(net);
Za = double(extractdata(predict(aeEnc, dlarray(single(((R - A.mu) ./ A.sd)'), 'CB'))))';
aeDecode = @(Z) double(extractdata(predict(aeDec, dlarray(single(Z'), 'CB'))))' .* A.sd + A.mu;
% VAE (prior N(0, I))
vaeDecode = @(Z) double(extractdata(forward(V.dec, dlarray(single(Z'), 'CB'))))' .* V.sd + V.mu;
reps = {
    'param3', [], lb3, ub3
    'pca', pcaDec, [min(Zp) lb3(2:3)], [max(Zp) ub3(2:3)]
    'autoencoder', aeDecode, [min(Za) lb3(2:3)], [max(Za) ub3(2:3)]
    'vae', vaeDecode, [-2.5*ones(1,k) lb3(2:3)], [2.5*ones(1,k) ub3(2:3)]};
rows = {};
for i = 1:size(reps,1)
    if isempty(reps{i,2})
        env = chute.bench.simulatorEnv(seeds, tag='latent-param3');
    else
        env = chute.bench.latentEnv(reps{i,2}, k, seeds, tag=['latent-' reps{i,1}]);
    end
    for r = 1:opts.nRuns
        res = runBoxed(opts.method, env, opts.budget, 500 + r, reps{i,3}, reps{i,4});
        rows(end+1,:) = {string(reps{i,1}), r, res.fbest, res.validGeometryRate, res.sensingFailureRate, res.requests, res.simulatedDrops}; %#ok<AGROW>
    end
end
T = cell2table(rows, 'VariableNames', {'representation','run','best_score','valid_geometry_rate','sensing_failure_rate','requests','simulated_drops'});
end

function res = runBoxed(method, env, budget, seed, lb, ub)
% same runner as the main benchmark, but with representation-specific bounds
rng(seed, 'twister');
obj = chute.bench.BudgetedObjective(env, budget);
d = numel(lb);
try
    switch method
        case 'bo'
            vars = arrayfun(@(j) optimizableVariable(sprintf('x%d', j), [lb(j) ub(j)]), 1:d);
            bayesopt(@(t) obj.eval(table2array(t)), vars, 'MaxObjectiveEvaluations', budget, 'IsObjectiveDeterministic', true, ...
                'Verbose', 0, 'PlotFcn', [], 'AcquisitionFunctionName', 'expected-improvement-plus');
        case 'ga'
            o = optimoptions('ga', 'PopulationSize', 10, 'UseVectorized', true, 'Display', 'off', 'MaxGenerations', 1e4);
            ga(@(X) obj.evalVec(X), d, [], [], [], [], lb, ub, [], o);
    end
catch e
    if ~strcmp(e.identifier, 'chute:budgetExhausted'), rethrow(e); end
end
res = obj.summary();
end

function enc = encoderOf(net)
L = net.Layers; ic = find(strcmp({L.Name}, 'code'));
enc = dlnetwork(L(1:ic));
end

function dec = decoderOf(net)
L = net.Layers; ic = find(strcmp({L.Name}, 'code'));
k = L(ic).OutputSize;
dec = dlnetwork([featureInputLayer(k); L(ic+1:end)]);
end
