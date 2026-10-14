function tabuSearch(obj, lb, ub, s)
%TABUSEARCH Tabu search over a discretized design grid. Neighbourhood: +/-1 grid step in each
%variable. Recently visited points are tabu (tenure) unless they beat the best (aspiration).
% Evaluated designs are memoized by the algorithm (no repeated requests for the same grid point).
if nargin < 4, s = struct(); end
steps = getf(s, 'steps', [0.5 0.025 0.05]);
tenure = getf(s, 'tenure', 7);
levels = arrayfun(@(i) numel(lb(i):steps(i):ub(i)), 1:3);
toX = @(g) min(lb + (g - 1) .* steps, ub);
memo = containers.Map('KeyType', 'char', 'ValueType', 'double');
key = @(g) sprintf('%d,', g);
    function f = val(g)
        k = key(g);
        if isKey(memo, k), f = memo(k); return; end
        f = obj.eval(toX(g)); memo(k) = f;
    end
cur = arrayfun(@(L) randi(L), levels);
fcur = val(cur); best = fcur;
tabu = zeros(0,3); stall = 0;
while true
    nb = zeros(0,3);
    for d = 1:3
        for sgn = [-1 1]
            g = cur; g(d) = g(d) + sgn;
            if g(d) >= 1 && g(d) <= levels(d), nb(end+1,:) = g; end %#ok<AGROW>
        end
    end
    fn = arrayfun(@(i) val(nb(i,:)), 1:size(nb,1))';
    isTabu = ismember(nb, tabu, 'rows');
    allowed = ~isTabu | fn < best;
    if ~any(allowed)
        cur = arrayfun(@(L) randi(L), levels); fcur = val(cur); continue;
    end
    fn(~allowed) = inf;
    [fmin, k] = min(fn);
    tabu = [tabu; cur]; if size(tabu,1) > tenure, tabu(1,:) = []; end %#ok<AGROW>
    cur = nb(k,:); fcur = fmin;
    if fcur < best, best = fcur; stall = 0; else, stall = stall + 1; end
    if stall > getf(s, 'restartAfter', 10)   % diversification restart
        cur = arrayfun(@(L) randi(L), levels); fcur = val(cur); stall = 0;
    end
end
end

function v = getf(s, name, default)
if isfield(s, name), v = s.(name); else, v = default; end
end
