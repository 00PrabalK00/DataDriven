%RUNALL Run the MATLAB test suite (from the repo root: matlab -batch "run('matlab/tests/runAll.m')").
here = fileparts(mfilename('fullpath'));
addpath(fileparts(here));
res = runtests(here);
disp(table(res));
assert(all([res.Passed]), 'MATLAB tests failed');
