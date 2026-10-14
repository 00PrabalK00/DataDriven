function logIteration(note, fitFile, calDrops, valDrops)
%LOGITERATION Append a real2sim iteration record. A refit after validation is a NEW iteration that
%requires fresh validation drops.
f = fullfile(chute.util.repoRoot(), 'results', 'calibration', 'iterations.jsonl');
if ~exist(fileparts(f), 'dir'), mkdir(fileparts(f)); end
rec = struct('time', char(datetime('now', 'Format', 'yyyy-MM-dd''T''HH:mm:ss')), 'note', note, ...
    'fit_file', fitFile, 'calibration_drops', {calDrops}, 'validation_drops', {valDrops});
fid = fopen(f, 'a'); fprintf(fid, '%s\n', jsonencode(rec)); fclose(fid);
end
