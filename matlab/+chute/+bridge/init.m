function init()
%INIT Start the persistent, separate Python process (pyenv OutOfProcess) used by the bridge.
root = chute.util.repoRoot();
exe = fullfile(root, 'python', '.venv', 'bin', 'python');
pe = pyenv;
if pe.Status == "Loaded" && ~strcmp(pe.Executable, exe)
    terminate(pyenv);
end
if pyenv().Status == "NotLoaded"
    if isempty(getenv('MUJOCO_GL')), setenv('MUJOCO_GL', 'egl'); end   % inherited by the Python process
    pyenv(Version=exe, ExecutionMode="OutOfProcess");
end
p = fullfile(root, 'python');
if count(py.sys.path, p) == 0
    insert(py.sys.path, int32(0), p);
end
end
