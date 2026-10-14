function P = pcaStudy(R, ks)
%PCASTUDY Linear compression of radial outlines: variance retained, reconstruction error and
%geometric validity of reconstructions for each latent size k.
if nargin < 2, ks = [2 3 4 6 8 12]; end
mu = mean(R, 1);
[coeff, score, ~, ~, explained] = pca(R);
P.explained = explained; P.mu = mu; P.coeff = coeff;
P.k = ks(:); P.rmse = zeros(numel(ks),1); P.validRate = zeros(numel(ks),1); P.varRetained = zeros(numel(ks),1);
for a = 1:numel(ks)
    k = ks(a);
    Rh = score(:,1:k) * coeff(:,1:k)' + mu;
    P.rmse(a) = sqrt(mean((Rh(:) - R(:)).^2));
    P.validRate(a) = mean(chute.rep.isValidShape(chute.rep.normalizeArea(Rh)));
    P.varRetained(a) = sum(explained(1:k));
end
P.table = table(P.k, P.varRetained, P.rmse, P.validRate, 'VariableNames', {'k','var_retained_pct','recon_rmse','valid_rate'});
end
