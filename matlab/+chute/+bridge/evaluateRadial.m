function [res, counters] = evaluateRadial(R, slits, seeds, opts)
%EVALUATERADIAL Evaluate free-form outlines (rows of R: r(theta)/R_eq, 64 samples; area is normalized
%to A0 by the simulator) with 4 radial slits (slits: N x 2 [slit_len, slit_r]) through the simulator
%and the shared sensing pipeline (L2).
arguments
    R double
    slits (:,2) double
    seeds (1,:) double
    opts.tag (1,:) char = 'radial'
    opts.n_workers double = []
end
n = size(R,1);
designs = cell(n,1);
for i = 1:n
    designs{i} = struct('radial', R(i,:), 'slit_len', slits(i,1), 'slit_r', slits(i,2));
end
req = struct('designs', {designs}, 'seeds', seeds, 'tag', opts.tag);
if ~isempty(opts.n_workers), req.n_workers = opts.n_workers; end
out = chute.bridge.call('evaluate_json', jsonencode(req));
res = out.results; if ~iscell(res), res = num2cell(res); end
counters = out.counters;
end
