function env = surrogateEnv(model, model2)
%SURROGATEENV Frozen-surrogate environment (separate benchmark: "surrogate environment").
% model/model2: objects with predict(X) (e.g. RegressionGP) for score and secondary objective.
env = @(X) callSur(X, model, model2);
end

function r = callSur(X, model, model2)
n = size(X,1);
[ok, ~] = deal(true(n,1));
r.score = predict(model, X); r.secondary = zeros(n,1);
if nargin > 2 && ~isempty(model2), r.secondary = predict(model2, X); end
r.status = repmat("ok", n, 1); r.status(~ok) = "infeasible_geometry";
r.drops = zeros(n,1); r.cacheHits = zeros(n,1);
end
