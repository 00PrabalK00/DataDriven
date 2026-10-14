function A = aeStudy(R, ks, opts)
%AESTUDY Nonlinear autoencoder (MLP) on radial outlines; reconstruction error and validity vs k on a
%held-out test split.
arguments
    R double
    ks double = [2 3 4 6 8]
    opts.epochs double = 300
    opts.seed double = 0
end
rng(opts.seed, 'twister');
n = size(R,1); te = false(n,1); te(randperm(n, round(0.2*n))) = true;
mu = mean(R(~te,:)); sd = std(R(~te,:)) + 1e-6;
Z = (R - mu) ./ sd;
A.k = ks(:); A.rmse = zeros(numel(ks),1); A.validRate = zeros(numel(ks),1); A.nets = cell(numel(ks),1);
for a = 1:numel(ks)
    k = ks(a); d = size(R,2);
    layers = [featureInputLayer(d) fullyConnectedLayer(48) tanhLayer fullyConnectedLayer(k, 'Name', 'code') ...
              fullyConnectedLayer(48) tanhLayer fullyConnectedLayer(d)];
    o = trainingOptions('adam', 'MaxEpochs', opts.epochs, 'MiniBatchSize', 128, 'Verbose', false, ...
        'InitialLearnRate', 3e-3, 'Shuffle', 'every-epoch');
    net = trainnet(Z(~te,:), Z(~te,:), layers, 'mse', o);
    Zh = predict(net, Z(te,:));
    Rh = Zh .* sd + mu;
    A.rmse(a) = sqrt(mean((Rh - R(te,:)).^2, 'all'));
    A.validRate(a) = mean(chute.rep.isValidShape(chute.rep.normalizeArea(Rh)));
    A.nets{a} = net;
end
A.mu = mu; A.sd = sd;
A.table = table(A.k, A.rmse, A.validRate, 'VariableNames', {'k','test_recon_rmse','valid_rate'});
end
