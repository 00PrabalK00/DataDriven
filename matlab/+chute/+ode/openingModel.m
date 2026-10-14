function K = openingModel(p)
%OPENINGMODEL Effective drag-area history K(t) (empirical fitting model, not an inflation model).
switch p.opening
    case 'exp'
        K = @(t) p.K_i + (p.K_o - p.K_i) .* (1 - exp(-max(t,0) ./ p.tau));
    case 'logistic'   % used only for deliberate model-mismatch studies
        K = @(t) p.K_i + (p.K_o - p.K_i) ./ (1 + exp(-(t - 1.5*p.tau) ./ (0.3*p.tau)));
    case 'linear'
        K = @(t) p.K_i + (p.K_o - p.K_i) .* min(max(t,0) ./ (2*p.tau), 1);
    otherwise
        error('chute:opening', 'unknown opening model %s', p.opening);
end
end
