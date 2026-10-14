%M9_BENCHMARK Milestone 9: optimizer comparison in the simulator environment (L2: synthetic benchmark
%under assumed aerodynamics). Set SMOKE=true for checkpoint B (2 methods x 2 runs x 25 evals).
run(fullfile(fileparts(mfilename('fullpath')), 'setupPaths.m'));
if ~exist('SMOKE', 'var'), SMOKE = true; end
if SMOKE
    B = chute.bench.runBenchmark(methods={'random','ga'}, nRuns=2, budget=25, nScenarios=2, ...
        freshScenarios=4, tag='smoke');
else
    % full volume only after the timing/storage pilot has been reviewed
    B = chute.bench.runBenchmark(nRuns=10, budget=200, nScenarios=5, tag='full');
end
disp(B.level); disp(B.envName); disp(B.table);
