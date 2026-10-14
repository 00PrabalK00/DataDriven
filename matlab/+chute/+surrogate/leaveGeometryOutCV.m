function T = leaveGeometryOutCV(X, y, geomId, names, nFolds)
%LEAVEGEOMETRYOUTCV Cross-validation in which all repeats of a geometry are held out together
%(never individual repeats/frames), so accuracy refers to previously unseen designs.
if nargin < 4, names = {'linear','quadratic','gp','ensemble'}; end
u = unique(geomId);
if nargin < 5, nFolds = numel(u); end
rng(0, 'twister');
fold = zeros(size(u)); fold(randperm(numel(u))) = mod(0:numel(u)-1, nFolds) + 1;
pred = nan(numel(y), numel(names));
for f = 1:nFolds
    te = ismember(geomId, u(fold == f));
    M = chute.surrogate.fitModels(X(~te,:), y(~te), names);
    for k = 1:numel(names)
        pred(te,k) = predict(M.(names{k}), X(te,:));
    end
end
rmse = sqrt(mean((pred - y).^2, 1, 'omitnan'))';
mae = mean(abs(pred - y), 1, 'omitnan')';
rc = arrayfun(@(k) corr(pred(:,k), y, 'Type', 'Spearman', 'Rows', 'complete'), 1:numel(names))';
T = table(string(names(:)), rmse, mae, rc, 'VariableNames', {'model','rmse','mae','rank_corr'});
end
