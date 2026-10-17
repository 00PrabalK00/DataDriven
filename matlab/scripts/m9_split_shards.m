%M9_SPLIT_SHARDS Move completed runs from the old per-shard files into per-job files, so the job queue
%skips them (it only re-scores them on fresh scenarios). The shard files are moved to shards_backup/.
run(fullfile(fileparts(mfilename('fullpath')), 'setupPaths.m'));
d = fullfile(chute.util.repoRoot(), 'results', 'benchmark_full');
jd = fullfile(d, 'jobs'); if ~exist(jd, 'dir'), mkdir(jd); end
bd = fullfile(d, 'shards_backup'); if ~exist(bd, 'dir'), mkdir(bd); end
for f = dir(fullfile(d, 'full_shard*_runs.mat'))'
    S = load(fullfile(f.folder, f.name));
    for i = 1:numel(S.runs)
        r = S.runs{i};
        out = fullfile(jd, sprintf('full_job_%s_%02d_runs.mat', r.method, r.runIndex));
        if isfile(out), continue; end
        runs = {r}; opts = S.opts; envName = S.envName; level = S.level; %#ok<NASGU>
        save(out, 'runs', 'opts', 'envName', 'level');
        fprintf('split %s run %d -> %s\n', r.method, r.runIndex, out);
    end
    movefile(fullfile(f.folder, f.name), fullfile(bd, f.name));
end
