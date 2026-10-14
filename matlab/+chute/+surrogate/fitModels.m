function M = fitModels(X, y, names)
%FITMODELS Candidate surrogates mapping design parameters -> objective/metric.
if nargin < 3, names = {'linear','quadratic','gp','ensemble'}; end
M = struct();
for k = 1:numel(names)
    switch names{k}
        case 'linear',    M.linear = fitlm(X, y, 'linear');
        case 'quadratic', M.quadratic = fitlm(X, y, 'quadratic');
        case 'gp',        M.gp = fitrgp(X, y, 'KernelFunction', 'ardsquaredexponential', 'Standardize', true);
        case 'ensemble',  M.ensemble = fitrensemble(X, y, 'Method', 'Bag', 'NumLearningCycles', 100);
    end
end
end
