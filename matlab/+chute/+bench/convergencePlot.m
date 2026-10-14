function convergencePlot(runs, budget, file, subtitleText)
%CONVERGENCEPLOT Best-so-far vs objective requests: median line and IQR band per method.
meth = cellfun(@(r) string(r.method), runs);
um = unique(meth, 'stable');
fig = figure('Visible', 'off', 'Position', [0 0 820 480]); hold on;
cols = lines(numel(um));
for i = 1:numel(um)
    R = runs(meth == um(i));
    M = nan(numel(R), budget);
    for k = 1:numel(R)
        t = R{k}.bestTrace(:)'; n = min(numel(t), budget);
        M(k,1:n) = t(1:n);
        if n < budget && n > 0, M(k,n+1:end) = t(n); end   % converged early: hold final value
    end
    q = prctile(M, [25 50 75], 1);
    x = 1:budget;
    ok = ~isnan(q(2,:));
    fill([x(ok) fliplr(x(ok))], [q(1,ok) fliplr(q(3,ok))], cols(i,:), 'FaceAlpha', 0.15, 'EdgeColor', 'none', 'HandleVisibility', 'off');
    plot(x(ok), q(2,ok), 'Color', cols(i,:), 'LineWidth', 1.8, 'DisplayName', um(i));
end
xline([25 50 100 200], ':', 'HandleVisibility', 'off');
xlabel('objective requests (cached evaluations included)'); ylabel('best score so far (lower = slower landing)');
legend('Location', 'northeast'); grid on; box on;
title({'Optimizer convergence (median, IQR band)', subtitleText}, 'FontSize', 10, 'Interpreter', 'none');
exportgraphics(fig, file); close(fig);
end
