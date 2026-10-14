function [res, counters] = evaluate(designs, seeds, opts)
%EVALUATE Evaluate designs (N x 3: q, slit_len, slit_r) on scenario seeds through the simulator +
%shared sensing pipeline. Returns per-design objective structs (score, status, ...) and counters.
arguments
    designs (:,3) double
    seeds (1,:) double
    opts.tag (1,:) char = 'matlab'
    opts.n_workers double = []
    opts.log_path (1,:) char = ''
    opts.keep_frames = []
    opts.overrides struct = struct()
end
req = struct('designs', {num2cell(designs, 2)}, 'seeds', seeds, 'tag', opts.tag);
req.designs = cellfun(@(r) r, req.designs, 'UniformOutput', false);
if ~isempty(opts.n_workers), req.n_workers = opts.n_workers; end
if ~isempty(opts.log_path), req.log_path = opts.log_path; end
if ~isempty(opts.keep_frames), req.keep_frames = logical(opts.keep_frames); end
if ~isempty(fieldnames(opts.overrides)), req.overrides = opts.overrides; end
out = chute.bridge.call('evaluate_json', jsonencode(req));
res = out.results;
if ~iscell(res), res = num2cell(res); end
counters = out.counters;
end
