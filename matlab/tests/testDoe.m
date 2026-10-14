function tests = testDoe
tests = functiontests(localfunctions);
end

function testLhsBoundsAndBaselines(tc)
[D, info] = chute.doe.lhsDesigns(16, 1);
[lb, ub] = chute.doe.bounds();
verifySize(tc, D, [18 3]);
verifyTrue(tc, all(D >= lb - 1e-12 & D <= ub + 1e-12, 'all'));
verifyEqual(tc, D(info.isBaseline, :), [2 0 0.45; 4 0 0.45]);
verifyTrue(tc, all(chute.doe.isFeasible(D)));
end

function testScheduleRandomizedBlocks(tc)
[D, info] = chute.doe.lhsDesigns(16, 1);
T = chute.doe.dropSchedule(D, info.isBaseline, 3, 5);
verifyEqual(tc, height(T), 54);
for b = 1:3
    verifyEqual(tc, sort(T.design(T.repeat == b))', 1:18);   % every design once per block
end
verifyNotEqual(tc, T.design(1:18)', 1:18);                      % randomized
verifyEqual(tc, nnz(T.baseline), 6);
T2 = chute.doe.dropSchedule(D, info.isBaseline, 3, 6);
verifyNotEqual(tc, T.design, T2.design);
end

function testDiscrepancyPrefersSpread(tc)
rng(0); good = lhsdesign(30, 3, 'criterion', 'maximin');
bad = 0.5 + 0.1 * rand(30, 3);
verifyLessThan(tc, chute.doe.centeredL2Discrepancy(good), chute.doe.centeredL2Discrepancy(bad));
end
