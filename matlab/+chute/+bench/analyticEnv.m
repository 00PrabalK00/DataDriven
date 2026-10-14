function env = analyticEnv(name)
%ANALYTICENV Cheap known-optimum test objectives for validating the harness itself (L1).
switch name
    case 'quadratic'   % minimum at (5, 0.12, 0.45)
        f = @(X) ((X(:,1)-5)/6).^2 + ((X(:,2)-0.12)/0.25).^2 + ((X(:,3)-0.45)/0.4).^2;
    case 'multimodal'
        f = @(X) ((X(:,1)-5)/6).^2 + 0.3*sin(3*pi*X(:,2)/0.25).^2 + ((X(:,3)-0.45)/0.4).^2;
    otherwise
        error('chute:env', 'unknown analytic env %s', name);
end
env = @(X) struct('score', f(X), 'secondary', X(:,2), 'status', repmat("ok", size(X,1), 1), ...
    'drops', ones(size(X,1),1), 'cacheHits', zeros(size(X,1),1));
end
