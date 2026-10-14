function res = runMethod(method, env, budget, seed, opts)
%RUNMETHOD Run one search method on an environment with a maximum evaluation budget.
% Every method gets the same bounds, design encoding, environment and budget; initial sampling and
% finite-difference evaluations count against the budget.
arguments
    method (1,:) char
    env function_handle
    budget (1,1) double = 200
    seed (1,1) double = 1
    opts.settings struct = struct()
end
rng(seed, 'twister');
[lb, ub] = chute.doe.bounds();
obj = chute.bench.BudgetedObjective(env, budget);
s = opts.settings;
converged = false; msg = '';
try
    switch lower(method)
        case 'random'
            while true
                obj.evalVec(lb + rand(10,3) .* (ub - lb));
            end
        case 'ga'
            pop = getf(s, 'PopulationSize', 20);
            o = optimoptions('ga', 'PopulationSize', pop, 'MaxGenerations', 10000, 'UseVectorized', true, ...
                'Display', 'off', 'MaxStallGenerations', getf(s, 'MaxStallGenerations', 50), 'FunctionTolerance', 0);
            ga(@(X) obj.evalVec(X), 3, [], [], [], [], lb, ub, [], o); converged = true;
        case 'sa'
            o = optimoptions('simulannealbnd', 'Display', 'off', 'MaxFunctionEvaluations', budget, ...
                'InitialTemperature', getf(s, 'InitialTemperature', 100), 'FunctionTolerance', 0, ...
                'MaxStallIterations', 1e6);
            x0 = lb + rand(1,3) .* (ub - lb);
            simulannealbnd(@(x) obj.eval(x), x0, lb, ub, o); converged = true;
        case 'pso'
            o = optimoptions('particleswarm', 'SwarmSize', getf(s, 'SwarmSize', 15), 'UseVectorized', true, ...
                'Display', 'off', 'MaxIterations', 1e5, 'MaxStallIterations', getf(s, 'MaxStallIterations', 50), 'FunctionTolerance', 0);
            particleswarm(@(X) obj.evalVec(X), 3, lb, ub, o); converged = true;
        case 'bo'
            vars = [optimizableVariable('q', [lb(1) ub(1)]), optimizableVariable('l', [lb(2) ub(2)]), ...
                    optimizableVariable('r', [lb(3) ub(3)])];
            bayesopt(@(t) obj.eval([t.q t.l t.r]), vars, 'MaxObjectiveEvaluations', budget, ...
                'IsObjectiveDeterministic', true, 'NumSeedPoints', getf(s, 'NumSeedPoints', 10), ...
                'AcquisitionFunctionName', 'expected-improvement-plus', 'Verbose', 0, 'PlotFcn', [], ...
                'UseParallel', false);
            converged = true;
        case 'tabu'
            chute.bench.tabuSearch(obj, lb, ub, s);
        case 'gradient'
            step = getf(s, 'FiniteDifferenceStepSize', 1e-2);
            o = optimoptions('fmincon', 'Algorithm', 'sqp', 'Display', 'off', ...
                'FiniteDifferenceStepSize', step, 'TypicalX', (lb+ub)/2, 'MaxFunctionEvaluations', budget);
            while true   % multistart within the budget
                x0 = lb + rand(1,3) .* (ub - lb);
                fmincon(@(x) obj.eval(x), x0, [], [], [], [], lb, ub, [], o);
            end
        case 'moo'
            o = optimoptions('gamultiobj', 'PopulationSize', getf(s, 'PopulationSize', 20), 'UseVectorized', true, ...
                'Display', 'off', 'MaxGenerations', 10000);
            gamultiobj(@(X) moo(obj, X), 3, [], [], [], [], lb, ub, [], o); converged = true;
        otherwise
            error('chute:method', 'unknown method %s', method);
    end
catch e
    if ~strcmp(e.identifier, 'chute:budgetExhausted'), rethrow(e); end
    msg = 'budget exhausted';
end
res = obj.summary();
res.method = method; res.seed = seed; res.budget = budget;
res.endedEarly = converged && obj.requests < budget;
res.stopReason = msg;
if res.endedEarly, res.stopReason = 'solver converged before the maximum budget'; end
end

function F = moo(obj, X)
[f, f2] = obj.evalVec(X);
F = [f f2];
end

function v = getf(s, name, default)
if isfield(s, name), v = s.(name); else, v = default; end
end
