function B = runBenchmark(opts)
%RUNBENCHMARK Compare search methods: same encoding, bounds, environment and maximum budget;
%nRuns independent runs each; best-so-far at 25/50/100/200; three counters; final designs re-scored
%on fresh scenarios. Outputs .mat, CSV table and convergence plot (median + IQR), all tagged with the
%evidence level.
arguments
    opts.methods (1,:) cell = {'random','ga','sa','pso','bo','tabu','gradient'}
    opts.nRuns (1,1) double = 10
    opts.budget (1,1) double = 200
    opts.env (1,:) char = 'simulator'        % simulator | surrogate | analytic:<name>
    opts.nScenarios (1,1) double = 5
    opts.surrogate = []
    opts.freshScenarios (1,1) double = 20
    opts.rescore (1,1) logical = true
    opts.outDir (1,:) char = fullfile(chute.util.repoRoot(), 'results', 'benchmark')
    opts.tag (1,:) char = 'bench'
    opts.nWorkers double = []                % Python worker processes for this benchmark instance
    opts.resume (1,1) logical = true         % checkpointing: skip (method, run) pairs already saved
    opts.runIndices double = []              % run only these run indices (default 1:nRuns); one job per run
end
cfg = chute.bridge.config();
switch true
    case strcmp(opts.env, 'simulator')
        seeds = cfg.objective.search_seed_base + (0:opts.nScenarios-1);
        logp = fullfile(opts.outDir, [opts.tag '_requests.jsonl']);
        env = chute.bench.simulatorEnv(seeds, tag=opts.tag, log_path=logp, n_workers=opts.nWorkers);
        level = 'L2'; envName = sprintf('simulator (%d fixed scenarios, common random numbers)', opts.nScenarios);
        fresh = @() chute.bench.simulatorEnv(cfg.objective.fresh_seed_base + (0:opts.freshScenarios-1), tag=[opts.tag '-fresh'], n_workers=opts.nWorkers);
    case strcmp(opts.env, 'surrogate')
        env = chute.bench.surrogateEnv(opts.surrogate);
        level = 'L2'; envName = 'surrogate environment (frozen; separate benchmark)';
        fresh = [];
    case startsWith(opts.env, 'analytic:')
        env = chute.bench.analyticEnv(extractAfter(opts.env, 'analytic:'));
        level = 'L1'; envName = opts.env; fresh = [];
end
if ~exist(opts.outDir, 'dir'), mkdir(opts.outDir); end
% run seeds depend only on (method, run) so shards and restarts reproduce the same runs
allMethods = {'random','ga','sa','pso','bo','tabu','gradient','moo'};
runsFile = fullfile(opts.outDir, [opts.tag '_runs.mat']);
runs = {};
if opts.resume && isfile(runsFile)
    S = load(runsFile, 'runs'); runs = S.runs;
    fprintf('resuming: %d completed runs found in %s\n', numel(runs), runsFile);
end
done = cellfun(@(r) sprintf('%s#%d', r.method, r.runIndex), runs, 'UniformOutput', false);
for m = 1:numel(opts.methods)
    gi = find(strcmp(allMethods, opts.methods{m}));
    ks = 1:opts.nRuns; if ~isempty(opts.runIndices), ks = opts.runIndices; end
    for k = ks
        if any(strcmp(done, sprintf('%s#%d', opts.methods{m}, k))), continue; end
        fprintf('[%s] %s run %d/%d\n', datestr(now, 'yyyy-mm-dd HH:MM:SS'), opts.methods{m}, k, opts.nRuns); %#ok<TNOW1,DATST>
        r = chute.bench.runMethod(opts.methods{m}, env, opts.budget, 1000*gi + k);
        r.runIndex = k;
        runs{end+1} = r; %#ok<AGROW>
        save(runsFile, 'runs', 'opts', 'envName', 'level');   % checkpoint after every run
        writeProgress(opts, runs);
    end
end
% fresh-scenario re-scoring of each run's best design
if opts.rescore && ~isempty(fresh)
    fenv = fresh();
    if ~iscell(runs) || isempty(runs), B = struct(); return; end
    Xb = cell2mat(cellfun(@(r) r.xbest, runs, 'UniformOutput', false)');
    [Xu, ~, iu] = unique(Xb, 'rows');
    rr = fenv(Xu);
    for i = 1:numel(runs)
        runs{i}.freshScore = rr.score(iu(i)); runs{i}.freshStatus = rr.status(iu(i)); runs{i}.freshSpeed = rr.meanSpeed(iu(i));
    end
end
B.runs = runs; B.envName = envName; B.level = level; B.opts = opts;
B.table = chute.bench.summarize(runs, opts.budget);
writetable(B.table, fullfile(opts.outDir, [opts.tag '_summary.csv']));
chute.bench.convergencePlot(runs, opts.budget, fullfile(opts.outDir, [opts.tag '_convergence.png']), ...
    sprintf('%s | %s', chute.util.evidenceLabel(level), envName));
save(fullfile(opts.outDir, [opts.tag '_runs.mat']), 'runs', 'opts', 'envName', 'level', 'B');
end

function writeProgress(opts, runs)
total = numel(opts.methods) * opts.nRuns;
if ~isempty(opts.runIndices), total = numel(opts.methods) * numel(opts.runIndices); end
p.tag = opts.tag; p.completed_runs = numel(runs); p.total_runs = total;
p.simulated_drops = sum(cellfun(@(r) r.simulatedDrops, runs));
p.requests = sum(cellfun(@(r) r.requests, runs));
p.updated = char(datetime('now', 'Format', 'yyyy-MM-dd HH:mm:ss'));
fid = fopen(fullfile(opts.outDir, [opts.tag '_progress.json']), 'w'); fprintf(fid, '%s', jsonencode(p)); fclose(fid);
end
