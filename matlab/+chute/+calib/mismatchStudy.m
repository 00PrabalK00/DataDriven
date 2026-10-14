function S = mismatchStudy(opts)
%MISMATCHSTUDY Real2sim calibration infrastructure validated synthetically, with deliberate model
%mismatch. Synthetic "real" drops come from a generator containing structure the fitted model lacks.
%Calibration and validation GEOMETRIES are disjoint. A geometry->K_open map (linear in geometry
%features) is fitted on calibration geometries, frozen, and used to predict landing speed of held-out
%geometries. Reports prediction error per mismatch type (evidence level L1).
arguments
    opts.mismatches (1,:) cell = {'none','logistic_opening','drag_exponent_1.8','velocity_porosity','line_elasticity','bias_drift'}
    opts.nGeom (1,1) double = 18
    opts.dropsPerGeom (1,1) double = 3
    opts.noiseSd (1,1) double = 0.01
    opts.seed (1,1) double = 7
    opts.outDir (1,:) char = fullfile(chute.util.repoRoot(), 'results', 'calibration')
end
cfg = chute.bridge.config();
Kbox = chute.util.payloadKbox(cfg);
[D, ~] = chute.doe.lhsDesigns(opts.nGeom - 2, opts.seed);
nG = size(D,1);
feat = zeros(nG, 3); Ktrue = zeros(nG,1); tauTrue = zeros(nG,1);
for i = 1:nG
    g = chute.geom.geometry(D(i,1), D(i,2), D(i,3));
    feat(i,:) = [g.features.c_iso, g.features.slit_total_len_norm, g.features.porosity_proxy];
    % hidden "true" geometry->K relation (deliberately NOT linear in the features)
    Ktrue(i) = g.aero.K_open_m2 * (1 + 0.15*sin(6*g.features.slit_total_len_norm)) ;
    tauTrue(i) = g.aero.tau_s;
end
rng(opts.seed, 'twister');
perm = randperm(nG); nCal = round(nG * 2/3);
cal = perm(1:nCal); val = perm(nCal+1:end);
S.calGeoms = cal; S.valGeoms = val;
rows = {};
for mi = 1:numel(opts.mismatches)
    mm = opts.mismatches{mi};
    Kfit = nan(nG,1); tauFit = nan(nG,1);
    vTrue = nan(nG, opts.dropsPerGeom);
    for i = 1:nG
        kk = zeros(opts.dropsPerGeom,1); tt = kk;
        for j = 1:opts.dropsPerGeom
            p = struct('m', 0.093, 'g', 9.81, 'rho', 1.204, 'K_i', 0.3*Ktrue(i), 'K_o', Ktrue(i), ...
                'tau', tauTrue(i), 'K_box', Kbox, 'h0', 4.0 + 0.02*randn, 'v0', 0);
            [t, h, tr] = chute.calib.syntheticHistory(p, mm, opts.noiseSd, 1000*mi + 10*i + j);
            vTrue(i,j) = tr.v_contact;
            if ismember(i, cal)
                p0 = p; p0.K_o = 0.012; p0.tau = 0.15; p0.K_i = 0.3*0.012;
                f = chute.ode.fitAero(t, h, p0, fit={'K_o','tau'}, lb=[1e-4 0.01], ub=[0.1 1]);
                kk(j) = f.K_o; tt(j) = f.tau;
            end
        end
        if ismember(i, cal), Kfit(i) = mean(kk); tauFit(i) = mean(tt); end
    end
    % frozen geometry -> parameter map, fitted on calibration geometries only
    mdlK = fitlm(feat(cal,:), Kfit(cal));
    tauHat = mean(tauFit(cal));
    pred = nan(numel(val),1); obs = mean(vTrue(val,:), 2);
    for a = 1:numel(val)
        i = val(a);
        Kp = predict(mdlK, feat(i,:));
        p = struct('m', 0.093, 'g', 9.81, 'rho', 1.204, 'K_i', 0.3*Kp, 'K_o', Kp, 'tau', tauHat, ...
            'K_box', Kbox, 'h0', 4.0, 'v0', 0);
        s = chute.ode.simulateDrop(p);
        pred(a) = s.v_contact;
    end
    e = pred - obs;
    rho = corr(pred, obs, 'Type', 'Spearman');
    rows(end+1,:) = {string(mm), sqrt(mean(e.^2)), mean(e), max(abs(e)), rho}; %#ok<AGROW>
    S.(matlab.lang.makeValidName(mm)) = struct('pred', pred, 'obs', obs, 'model', mdlK);
end
S.table = cell2table(rows, 'VariableNames', {'mismatch','rmse_mps','bias_mps','maxabs_mps','rank_corr'});
S.evidence = [chute.util.evidenceLabel('L1') ' | real2sim calibration infrastructure validated synthetically'];
if ~exist(opts.outDir, 'dir'), mkdir(opts.outDir); end
writetable(S.table, fullfile(opts.outDir, 'mismatch_study.csv'));
end
