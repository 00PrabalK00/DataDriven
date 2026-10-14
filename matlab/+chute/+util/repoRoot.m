function r = repoRoot()
%REPOROOT Absolute path of the DataDriven repository.
r = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
end
