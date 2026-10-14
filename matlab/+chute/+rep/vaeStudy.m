function V = vaeStudy(R, k, opts)
%VAESTUDY Variational autoencoder on radial outlines (custom training loop). Generates new candidate
%shapes by sampling the latent prior; reports validity rate and diversity of generated shapes.
% Generated shapes must still pass area normalization and fabrication checks before evaluation.
arguments
    R double
    k double = 4
    opts.epochs double = 300
    opts.beta double = 0.05
    opts.nGenerate double = 500
    opts.seed double = 0
end
rng(opts.seed, 'twister');
d = size(R,2);
mu = mean(R); sd = std(R) + 1e-6;
X = dlarray(single(((R - mu) ./ sd)'), 'CB');
enc = dlnetwork([featureInputLayer(d) fullyConnectedLayer(64) tanhLayer fullyConnectedLayer(2*k)]);
dec = dlnetwork([featureInputLayer(k) fullyConnectedLayer(64) tanhLayer fullyConnectedLayer(d)]);
[ae, ad, de, dd] = deal([]);
n = size(R,1); bs = 128; it = 0;
for ep = 1:opts.epochs
    p = randperm(n);
    for s = 1:bs:n
        it = it + 1;
        xb = X(:, p(s:min(s+bs-1,n)));
        [loss, ge, gd] = dlfeval(@vaeLoss, enc, dec, xb, k, opts.beta); %#ok<ASGLU>
        [enc, ae, de] = adamupdate(enc, ge, ae, de, it, 2e-3);
        [dec, ad, dd] = adamupdate(dec, gd, ad, dd, it, 2e-3);
    end
end
zs = dlarray(single(randn(k, opts.nGenerate)), 'CB');
G = double(extractdata(forward(dec, zs)))' .* sd + mu;
G = chute.rep.normalizeArea(G);
V.generated = G;
V.validRate = mean(chute.rep.isValidShape(G));
Gv = G(chute.rep.isValidShape(G), :);
V.diversity = mean(pdist(Gv));
V.dataDiversity = mean(pdist(R(randperm(n, min(n, 500)), :)));
V.enc = enc; V.dec = dec; V.mu = mu; V.sd = sd; V.k = k;
end

function [loss, ge, gd] = vaeLoss(enc, dec, x, k, beta)
h = forward(enc, x);
m = h(1:k,:); lv = h(k+1:end,:);
z = m + exp(0.5*lv) .* randn(size(m), 'like', m);
xh = forward(dec, z);
rec = mean(sum((xh - x).^2, 1));
kl = mean(-0.5 * sum(1 + lv - m.^2 - exp(lv), 1));
loss = rec + beta * kl;
[ge, gd] = dlgradient(loss, enc.Learnables, dec.Learnables);
end
