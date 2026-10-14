function files = exportTemplate(q, slitLen, slitR, outDir, label)
%EXPORTTEMPLATE 1:1 cutting template (SVG in mm, plus DXF R12) with outline, slits, line
%attachment patches and a label. Net area is printed on the template for checking.
if nargin < 5, label = sprintf('q%.3f_l%.3f_r%.3f', q, slitLen, slitR); end
g = chute.geom.geometry(q, slitLen, slitR);
cfg = chute.bridge.config();
P = g.outline_m * 1000; S = reshape(g.slits_m, [], 2, 2) * 1000; A = g.attach_points_m * 1000;
pr = cfg.canopy.attach_patch_radius_m * 1000;
if ~exist(outDir, 'dir'), mkdir(outDir); end
m = max(abs(P(:))) + 15; W = 2*m;
svg = fullfile(outDir, [label '.svg']);
f = fopen(svg, 'w');
fprintf(f, '<svg xmlns="http://www.w3.org/2000/svg" width="%.2fmm" height="%.2fmm" viewBox="%.2f %.2f %.2f %.2f">\n', W, W, -m, -m, W, W);
fprintf(f, '<polygon fill="none" stroke="black" stroke-width="0.2" points="%s"/>\n', ...
    strjoin(arrayfun(@(i) sprintf('%.3f,%.3f', P(i,1), -P(i,2)), 1:size(P,1), 'UniformOutput', false), ' '));
for k = 1:size(S,1)
    fprintf(f, '<line x1="%.3f" y1="%.3f" x2="%.3f" y2="%.3f" stroke="red" stroke-width="0.2"/>\n', S(k,1,1), -S(k,1,2), S(k,2,1), -S(k,2,2));
end
for k = 1:size(A,1)
    fprintf(f, '<circle cx="%.3f" cy="%.3f" r="%.3f" fill="none" stroke="blue" stroke-width="0.2"/>\n', A(k,1), -A(k,2), pr);
end
fprintf(f, '<text x="%.1f" y="%.1f" font-size="4">%s  net area %.2f cm2  (1:1, mm)</text>\n', -m+3, m-3, label, g.area_net_m2*1e4);
fprintf(f, '</svg>\n'); fclose(f);
dxf = fullfile(outDir, [label '.dxf']);
f = fopen(dxf, 'w');
fprintf(f, '0\nSECTION\n2\nENTITIES\n');
n = size(P,1);
for i = 1:n
    j = mod(i, n) + 1;
    fprintf(f, '0\nLINE\n8\nOUTLINE\n10\n%.4f\n20\n%.4f\n11\n%.4f\n21\n%.4f\n', P(i,1), P(i,2), P(j,1), P(j,2));
end
for k = 1:size(S,1)
    fprintf(f, '0\nLINE\n8\nSLITS\n10\n%.4f\n20\n%.4f\n11\n%.4f\n21\n%.4f\n', S(k,1,1), S(k,1,2), S(k,2,1), S(k,2,2));
end
for k = 1:size(A,1)
    fprintf(f, '0\nCIRCLE\n8\nATTACH\n10\n%.4f\n20\n%.4f\n40\n%.4f\n', A(k,1), A(k,2), pr);
end
fprintf(f, '0\nENDSEC\n0\nEOF\n'); fclose(f);
files = {svg, dxf};
end
