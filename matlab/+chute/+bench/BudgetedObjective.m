classdef BudgetedObjective < handle
    %BUDGETEDOBJECTIVE Wraps an evaluation environment for one optimizer run.
    % - maximum `budget` objective REQUESTS (cached evaluations still count as requests)
    % - three counters: requests, unique designs, actual simulated drops
    % - best-so-far trace and checkpoints (25/50/100/200)
    % - raises 'chute:budgetExhausted' once the budget is used (runners catch it)
    properties
        env                 % function handle: X (n x 3) -> struct with fields score,status,drops,cacheHits,secondary
        budget = 200
        requests = 0
        simulatedDrops = 0
        cacheHits = 0
        X = zeros(0,3)
        F = zeros(0,1)
        F2 = zeros(0,1)     % secondary objective (stability proxy) for multi-objective runs
        status = strings(0,1)
        keys = strings(0,1)
        bestTrace = zeros(0,1)
        t0
        wall = zeros(0,1)
        zeroSlitR = 0.45
    end
    methods
        function obj = BudgetedObjective(env, budget)
            obj.env = env;
            if nargin > 1, obj.budget = budget; end
            obj.t0 = tic;
        end
        function f = eval(obj, x)
            f = obj.evalVec(x(:)');
        end
        function [f, f2] = evalVec(obj, X)
            n = size(X,1);
            remaining = obj.budget - obj.requests;
            if remaining <= 0
                error('chute:budgetExhausted', 'evaluation budget of %d used', obj.budget);
            end
            m = min(n, remaining);
            if isempty(obj.X) && size(obj.X,2) ~= size(X,2)
                obj.X = zeros(0, size(X,2));   % latent encodings have k + 2 columns, not 3
            end
            r = obj.env(X(1:m,:));
            f = inf(n,1); f2 = inf(n,1);
            f(1:m) = r.score(:); f2(1:m) = r.secondary(:);
            for i = 1:m
                obj.requests = obj.requests + 1;
                obj.X(end+1,:) = X(i,:);
                obj.F(end+1,1) = r.score(i);
                obj.F2(end+1,1) = r.secondary(i);
                obj.status(end+1,1) = string(r.status(i));
                obj.keys(end+1,1) = obj.canonicalKey(X(i,:));
                obj.simulatedDrops = obj.simulatedDrops + r.drops(i);
                obj.cacheHits = obj.cacheHits + r.cacheHits(i);
                prev = inf; if ~isempty(obj.bestTrace), prev = obj.bestTrace(end); end
                obj.bestTrace(end+1,1) = min(prev, r.score(i));
                obj.wall(end+1,1) = toc(obj.t0);
            end
            if m < n
                error('chute:budgetExhausted', 'evaluation budget of %d used', obj.budget);
            end
        end
        function k = canonicalKey(obj, x)
            % slit length / slit radius are the last two columns in every encoding
            if x(end-1) == 0, x(end) = obj.zeroSlitR; end
            k = string(strjoin(cellstr(num2hex(x(:))), '-'));
        end
        function s = summary(obj)
            [fb, ib] = min(obj.F);
            s.requests = obj.requests;
            s.uniqueDesigns = numel(unique(obj.keys));
            s.simulatedDrops = obj.simulatedDrops;
            s.cacheHits = obj.cacheHits;
            s.fbest = fb; s.xbest = obj.X(ib,:);
            s.bestTrace = obj.bestTrace;
            s.validGeometryRate = mean(obj.status ~= "infeasible_geometry");
            s.sensingFailureRate = mean(obj.status == "infeasible_sensing");
            s.wall_s = toc(obj.t0);
            cps = [25 50 100 200];
            s.checkpoints = cps;
            s.bestAt = arrayfun(@(c) obj.bestTrace(min(c, numel(obj.bestTrace))), cps);
            s.bestAt(cps > numel(obj.bestTrace)) = NaN;  % run ended earlier (converged)
            s.X = obj.X; s.F = obj.F; s.F2 = obj.F2; s.status = obj.status;
        end
    end
end
