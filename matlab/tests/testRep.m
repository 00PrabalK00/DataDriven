function tests = testRep
tests = functiontests(localfunctions);
end

function testShapeDatasetAreaAndValidity(tc)
[R, info] = chute.rep.shapeDataset(200, 1);
n = size(R,2); dth = 2*pi/n;
A = 0.5 * sin(dth) * sum(R .* circshift(R, -1, 2), 2);
verifyLessThan(tc, max(abs(A - pi)), 1e-9);
verifyGreaterThan(tc, mean(info.valid), 0.7);
end

function testPcaMonotone(tc)
R = chute.rep.shapeDataset(300, 2);
P = chute.rep.pcaStudy(R, [2 4 8]);
verifyTrue(tc, issorted(flip(P.rmse)));
end

function testSobolKnownFunction(tc)
f = @(X) X(:,1) + 2*X(:,2);          % no interaction, x3 inert
S = chute.analysis.sobolIndices(f, [0 0 0], [1 1 1], 20000);
verifyEqual(tc, S.first, [0.2 0.8 0], 'AbsTol', 0.05);
verifyLessThan(tc, S.total(3), 0.02);
end

function testSobolLargeOffset(tc)
% realistic case: a large mean (~6.85) with small variation between designs
f = @(X) 6.85 + 0.01 * (X(:,1) + 2*X(:,2));
S = chute.analysis.sobolIndices(f, [0 0 0], [1 1 1], 20000);
verifyEqual(tc, S.first, [0.2 0.8 0], 'AbsTol', 0.05);
verifyLessThanOrEqual(tc, max(S.first), 1.05);
end

function testLeaveGeometryOut(tc)
rng(1); X = rand(60,3); g = repelem((1:20)', 3); y = X(:,1).^2 + 0.01*randn(60,1);
T = chute.surrogate.leaveGeometryOutCV(X, y, g, {'linear','quadratic'}, 5);
verifyLessThan(tc, T.rmse(T.model=="quadratic"), T.rmse(T.model=="linear"));
end

function testHypervolumeKnown(tc)
[hv, ~, front] = chute.analysis.hypervolume2d([1 3; 2 2; 3 1; 2.5 2.5], [4 4]);
verifyEqual(tc, size(front,1), 3);
verifyEqual(tc, hv, 3*1 + 2*1 + 1*1, 'AbsTol', 1e-12);   % staircase area
end
