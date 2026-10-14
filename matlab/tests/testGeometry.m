function tests = testGeometry
tests = functiontests(localfunctions);
end

function testNetAreaExact(tc)
for x = [2 0 0.45; 3.5 0.1 0.3; 8 0.25 0.65; 5 0.25 0.25]'
    g = chute.geom.geometry(x(1), x(2), x(3));
    verifyLessThan(tc, abs(g.area_net_m2 - 0.025), 1e-9);
end
end

function testQ2IsCircle(tc)
g = chute.geom.geometry(2, 0, 0.45);
r = vecnorm(g.outline_m, 2, 2);
verifyLessThan(tc, std(r) / mean(r), 1e-10);
end

function testZeroSlitCanonical(tc)
a = chute.geom.geometry(3, 0, 0.3); b = chute.geom.geometry(3, 0, 0.6);
verifyEqual(tc, a.polygon_hash, b.polygon_hash);
end

function testInfeasibleRejected(tc)
g = chute.geom.geometry(9, 0.1, 0.4);
verifyFalse(tc, g.feasible);
end

function testTemplateExport(tc)
d = tempname; files = chute.geom.exportTemplate(4, 0.15, 0.45, d, 'test');
verifyTrue(tc, isfile(files{1}) && isfile(files{2}));
verifySubstring(tc, fileread(files{1}), 'net area 250.00 cm2');
end
