function T = summarize(runs, budget)
%SUMMARIZE Per-method results table: median/IQR best at checkpoints, evaluations to reach a target
%(within 1% of the best value any run found), counters, failure rates, runtime, fresh re-score.
meth = cellfun(@(r) string(r.method), runs);
um = unique(meth, 'stable');
% target: within 10% of the gap between a typical valid design (median of all valid evaluations)
% and the best value any run found -- a relative 1% target is meaningless when designs differ by
% only a few hundredths of a m/s
fAll = min(cellfun(@(r) r.fbest, runs));
allF = cell2mat(cellfun(@(r) r.F(r.status == "ok"), runs, 'UniformOutput', false)');
target = fAll + 0.1 * (median(allF) - fAll);
% multi-objective quality: hypervolume / spacing of each run's non-dominated set (valid points only)
isMoo = cellfun(@(r) strcmp(r.method, 'moo'), runs);
ref = [NaN NaN];
if any(isMoo)
    allF = cell2mat(cellfun(@(r) [r.F r.F2], runs(isMoo), 'UniformOutput', false)');
    ok = cell2mat(cellfun(@(r) r.status == "ok", runs(isMoo), 'UniformOutput', false)');
    ref = max(allF(ok, :), [], 1) * 1.05;
end
rows = {};
for m = um
    R = runs(meth == m);
    bestAt = cell2mat(cellfun(@(r) r.bestAt, R, 'UniformOutput', false)');
    fb = cellfun(@(r) r.fbest, R);
    e2t = cellfun(@(r) firstHit(r.bestTrace, target), R);
    row = {m, numel(R), median(fb), iqr(fb), median(bestAt(:,1),'omitnan'), median(bestAt(:,2),'omitnan'), ...
        median(bestAt(:,3),'omitnan'), median(bestAt(:,4),'omitnan'), median(e2t, 'omitnan'), mean(~isnan(e2t)), ...
        median(cellfun(@(r) r.requests, R)), median(cellfun(@(r) r.uniqueDesigns, R)), ...
        median(cellfun(@(r) r.simulatedDrops, R)), mean(cellfun(@(r) r.validGeometryRate, R)), ...
        mean(cellfun(@(r) r.sensingFailureRate, R)), median(cellfun(@(r) r.wall_s, R)), ...
        mean(cellfun(@(r) r.endedEarly, R)), median(cellfun(@(r) getfieldd(r, 'freshScore'), R), 'omitnan'), ...
        median(cellfun(@(r) hvOf(r, ref), R), 'omitnan'), median(cellfun(@(r) spOf(r, ref), R), 'omitnan')};
    rows(end+1,:) = row; %#ok<AGROW>
end
T = cell2table(rows, 'VariableNames', {'method','runs','best_median','best_iqr','best_at25','best_at50', ...
    'best_at100','best_at200','evals_to_target_median','frac_reached_target','requests_median', ...
    'unique_designs_median','simulated_drops_median','valid_geometry_rate','sensing_failure_rate', ...
    'wall_s_median','frac_ended_early','fresh_score_median','hypervolume_median','spacing_median'});
end

function k = firstHit(trace, target)
k = find(trace <= target, 1);
if isempty(k), k = NaN; end
end

function v = getfieldd(s, f)
if isfield(s, f), v = s.(f); else, v = NaN; end
end

function h = hvOf(r, ref)
if ~strcmp(r.method, 'moo') || any(isnan(ref)), h = NaN; return; end
ok = r.status == "ok";
h = chute.analysis.hypervolume2d([r.F(ok) r.F2(ok)], ref);
end

function s = spOf(r, ref)
if ~strcmp(r.method, 'moo') || any(isnan(ref)), s = NaN; return; end
ok = r.status == "ok";
[~, s] = chute.analysis.hypervolume2d([r.F(ok) r.F2(ok)], ref);
end
