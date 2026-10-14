function R = flightClusters(F, featNames, kRange)
%FLIGHTCLUSTERS PCA summary and k-means grouping of measured flight-feature vectors (rows of F).
% PCA: dimensionality/variance retained. k-means: behaviour groups, k chosen by mean silhouette.
if nargin < 3, kRange = 2:6; end
Z = normalize(F);
[coeff, score, ~, ~, explained] = pca(Z);
R.pca.coeff = coeff; R.pca.explained = explained; R.pca.score = score;
R.pca.nFor90 = find(cumsum(explained) >= 90, 1);
sil = nan(size(kRange)); idxAll = cell(size(kRange));
for a = 1:numel(kRange)
    k = kRange(a);
    if k >= size(Z,1), continue; end
    idx = kmeans(Z, k, 'Replicates', 20, 'Options', statset('MaxIter', 500));
    s = silhouette(Z, idx); sil(a) = mean(s); idxAll{a} = idx;
end
[R.bestSilhouette, b] = max(sil);
R.k = kRange(b); R.idx = idxAll{b}; R.silhouette = sil; R.kRange = kRange;
R.centroids = array2table(splitapply(@(x) mean(x,1), F, R.idx), 'VariableNames', featNames);
R.meaningful = R.bestSilhouette > 0.5;   % common rule of thumb for strong structure
end
