function r = recoveryTest(nTrials, noiseSd)
%RECOVERYTEST Parameter recovery when data come from the SAME model as the fit. This checks the
%implementation only (L1); it is not evidence of physical accuracy.
if nargin < 1, nTrials = 20; end
if nargin < 2, noiseSd = 0.01; end
cfg = chute.bridge.config();
Kbox = chute.util.payloadKbox(cfg);
err = zeros(nTrials, 2); covered = false(nTrials, 2); cc = zeros(nTrials,1);
for k = 1:nTrials
    rng(k);
    p = struct('m', 0.093, 'g', 9.81, 'rho', 1.204, 'K_i', 0.004, 'K_o', 0.010 + 0.01*rand, ...
        'tau', 0.08 + 0.15*rand, 'K_box', Kbox, 'h0', 4.0, 'v0', 0);
    [t, h] = chute.calib.syntheticHistory(p, 'none', noiseSd, k);
    p0 = p; p0.K_o = 0.015; p0.tau = 0.15;
    f = chute.ode.fitAero(t, h, p0, fit={'K_o','tau'}, lb=[1e-4 0.01], ub=[0.1 1]);
    err(k,:) = [f.K_o - p.K_o, f.tau - p.tau];
    cc(k) = abs(f.corr(1,2));
    covered(k,:) = [p.K_o >= f.ci95(1,1) && p.K_o <= f.ci95(2,1), p.tau >= f.ci95(1,2) && p.tau <= f.ci95(2,2)];
end
r.relErrK = abs(err(:,1)) ./ 0.015;
r.coverage95 = mean(covered);
r.meanAbsCorr = mean(cc);   % K_o-tau correlation: near 1 means only a combination is identifiable
r.medianAbsErr = median(abs(err));
r.evidence = chute.util.evidenceLabel('L1');
end
