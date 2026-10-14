function tests = testOde
tests = functiontests(localfunctions);
end

function testTerminalSpeedLimit(tc)
p = struct('m', 0.15, 'g', 9.81, 'rho', 1.2, 'K_i', 0.02, 'K_o', 0.02, 'tau', 0.1, 'K_box', 0, 'h0', 200, 'v0', 0, 'tmax', 60);
s = chute.ode.simulateDrop(p);
verifyEqual(tc, s.v_contact, s.v_terminal_open, 'RelTol', 1e-3);
end

function testFitAeroRecoversOwnModelNoiseFree(tc)
% implementation check: same model, no noise -> exact recovery
p = struct('m', 0.093, 'g', 9.81, 'rho', 1.204, 'K_i', 0.004, 'K_o', 0.015, 'tau', 0.15, 'K_box', 0.0067, 'h0', 4.0, 'v0', 0);
[t, h] = chute.calib.syntheticHistory(p, 'none', 0, 1);
p0 = p; p0.K_o = 0.01; p0.tau = 0.3;
f = chute.ode.fitAero(t, h, p0, fit={'K_o','tau'}, lb=[1e-4 0.01], ub=[0.1 1]);
verifyEqual(tc, f.K_o, 0.015, 'RelTol', 0.02);
verifyEqual(tc, f.tau, 0.15, 'RelTol', 0.1);
end

function testFitAeroNoisyCoverage(tc)
% with 1 cm noise K_o and tau are strongly correlated in a 2.5 m drop (identifiability limit);
% the confidence intervals must still be honest (cover the truth most of the time)
r = chute.calib.recoveryTest(8, 0.01);
verifyGreaterThanOrEqual(tc, min(r.coverage95), 0.6);
verifyGreaterThan(tc, r.meanAbsCorr, 0.9);   % documents the identifiability problem
end

function testMismatchStudyReport(tc)
S = chute.calib.mismatchStudy(nGeom=9, dropsPerGeom=2, outDir=tempname);
verifyEqual(tc, height(S.table), 6);
verifyEmpty(tc, intersect(S.calGeoms, S.valGeoms));           % disjoint geometries
verifySubstring(tc, S.evidence, 'validated synthetically');
none = S.table(S.table.mismatch == "none", :);
verifyLessThan(tc, none.rmse_mps, max(S.table.rmse_mps) + 1e-12);
end

function testMujocoMatchesOde45(tc)
v = chute.bridge.call('vertical_drop_json', 4, 0.15, 0.45, int32(1000));
p = struct('m', v.m, 'g', v.g, 'rho', v.rho, 'K_i', v.K_i, 'K_o', v.K_o, 'tau', v.tau, 'K_box', v.K_box, 'h0', v.h0, 'v0', 0);
s = chute.ode.simulateDrop(p);
verifyEqual(tc, v.v_contact, s.v_contact, 'RelTol', 0.01);
end

function testSplitDisjoint(tc)
ids = repelem(1:18, 3)';
[cal, val] = chute.calib.splitGeometries(ids, 2/3, 1);
verifyEmpty(tc, intersect(unique(ids(cal)), unique(ids(val))));
end
