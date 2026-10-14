function tests = testBench
tests = functiontests(localfunctions);
end

function testBudgetCapAllMethods(tc)
env = chute.bench.analyticEnv('quadratic');
for m = {'random','ga','sa','pso','bo','tabu','gradient','moo'}
    r = chute.bench.runMethod(m{1}, env, 40, 1);
    verifyLessThanOrEqual(tc, r.requests, 40, m{1});
    if ~r.endedEarly
        verifyEqual(tc, r.requests, 40, m{1});
    end
end
end

function testFiniteDifferenceCallsCounted(tc)
calls = 0;
    function out = env(X)
        calls = calls + size(X,1);
        out = struct('score', sum(X.^2, 2), 'secondary', zeros(size(X,1),1), 'status', repmat("ok", size(X,1), 1), ...
            'drops', ones(size(X,1),1), 'cacheHits', zeros(size(X,1),1));
    end
r = chute.bench.runMethod('gradient', @env, 50, 2);
verifyEqual(tc, r.requests, 50);
verifyEqual(tc, calls, 50);      % every finite-difference evaluation is a counted request
end

function testCachedRequestsCountedAndCountersConsistent(tc)
seen = containers.Map();
    function out = env(X)
        n = size(X,1); hits = zeros(n,1); drops = zeros(n,1);
        for i = 1:n
            k = mat2str(X(i,:), 17);
            if isKey(seen, k), hits(i) = 1; else, drops(i) = 1; seen(k) = 1; end
        end
        out = struct('score', sum(X,2), 'secondary', zeros(n,1), 'status', repmat("ok", n, 1), 'drops', drops, 'cacheHits', hits);
    end
o = chute.bench.BudgetedObjective(@env, 10);
x = [4 0.1 0.4];
o.evalVec([x; x; x]);
o.evalVec([4 0 0.3; 4 0 0.6]);          % zero-slit: same canonical design
s = o.summary();
verifyEqual(tc, s.requests, 5);
verifyEqual(tc, s.uniqueDesigns, 2);
verifyEqual(tc, s.simulatedDrops + s.cacheHits, s.requests);   % 1 scenario per request here
verifyEqual(tc, s.cacheHits, 2);
end

function testBudgetExhaustionError(tc)
o = chute.bench.BudgetedObjective(chute.bench.analyticEnv('quadratic'), 3);
o.evalVec(rand(3,3) .* [6 0.25 0.4] + [2 0 0.25]);
verifyError(tc, @() o.eval([4 0.1 0.4]), 'chute:budgetExhausted');
end

function testAnalyticBenchmarkSmoke(tc)
B = chute.bench.runBenchmark(methods={'random','tabu'}, nRuns=2, budget=25, env='analytic:quadratic', ...
    outDir=tempname, tag='l1');
verifyEqual(tc, height(B.table), 2);
verifyEqual(tc, B.level, 'L1');
end
