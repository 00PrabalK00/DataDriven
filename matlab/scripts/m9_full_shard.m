%M9_FULL_SHARD Full-volume optimizer benchmark (L2), one shard of methods per MATLAB process.
% Set SHARD = 1|2|3|4 before running. Resumable: rerun the same shard after any interruption.
run(fullfile(fileparts(mfilename('fullpath')), 'setupPaths.m'));
shards = {{'random','ga','pso'}, {'sa','bo'}, {'tabu','gradient'}, {'moo'}};
workers = [10 5 5 10];
B = chute.bench.runBenchmark(methods=shards{SHARD}, nRuns=10, budget=200, nScenarios=5, ...
    freshScenarios=20, tag=sprintf('full_shard%d', SHARD), nWorkers=workers(SHARD), ...
    outDir=fullfile(chute.util.repoRoot(), 'results', 'benchmark_full'));
disp(B.table);
