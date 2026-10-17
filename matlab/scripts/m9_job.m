%M9_JOB One (method, run) of the full benchmark (L2) as its own resumable job.
% Set METHOD (char) and RUNK (1..10) before running. Output: results/benchmark_full/jobs/full_job_<method>_<k>_*.
% The run seed depends only on (method, run), so jobs reproduce the same runs as the old shards.
run(fullfile(fileparts(mfilename('fullpath')), 'setupPaths.m'));
nw = 5; if strcmp(METHOD, 'random') || strcmp(METHOD, 'ga') || strcmp(METHOD, 'pso') || strcmp(METHOD, 'moo'), nw = 10; end
B = chute.bench.runBenchmark(methods={METHOD}, nRuns=10, runIndices=RUNK, budget=200, nScenarios=5, ...
    freshScenarios=20, tag=sprintf('full_job_%s_%02d', METHOD, RUNK), nWorkers=nw, ...
    outDir=fullfile(chute.util.repoRoot(), 'results', 'benchmark_full', 'jobs'));
disp(B.table);
fprintf('JOB DONE %s %d\n', METHOD, RUNK);
