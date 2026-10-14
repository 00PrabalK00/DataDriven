function T = dropSchedule(D, isBaseline, nRep, seed)
%DROPSCHEDULE Randomized physical drop order. Each of nRep blocks contains every design once in
%random order, so baselines are interleaved through the session (exposes drift in release technique
%or material condition). 18 designs x 3 repeats = 54 drops.
rng(seed, 'twister');
nD = size(D,1); rows = [];
for b = 1:nRep
    p = randperm(nD)';
    rows = [rows; [p, repmat(b, nD, 1)]]; %#ok<AGROW>
end
T = table((1:size(rows,1))', rows(:,1), rows(:,2), D(rows(:,1),1), D(rows(:,1),2), D(rows(:,1),3), ...
    isBaseline(rows(:,1)), repmat("", size(rows,1), 1), ...
    'VariableNames', {'drop','design','repeat','q','slit_len','slit_r','baseline','failure_label'});
end
