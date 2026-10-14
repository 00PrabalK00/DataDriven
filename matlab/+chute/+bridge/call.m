function out = call(fn, varargin)
%CALL Call chutesim.bridge.<fn>(args...) in the persistent Python process; jsondecode the result.
chute.bridge.init();
r = feval(['py.chutesim.bridge.' fn], varargin{:});
out = jsondecode(char(r));
end
