function cfg = config()
%CONFIG Project configuration (config/defaults.json), read directly (no Python needed).
cfg = jsondecode(fileread(fullfile(chute.util.repoRoot(), 'config', 'defaults.json')));
end
