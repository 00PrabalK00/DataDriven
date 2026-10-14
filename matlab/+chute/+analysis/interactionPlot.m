function interactionPlot(f, lb, ub, names, file, subtitleText)
%INTERACTIONPLOT Two-variable response maps (third variable at its mid value) of a vectorized f.
pairs = [1 2; 1 3; 2 3];
fig = figure('Visible', 'off', 'Position', [0 0 1200 360]);
tiledlayout(1,3);
mid = (lb + ub) / 2;
for p = 1:3
    i = pairs(p,1); j = pairs(p,2);
    [A, B] = meshgrid(linspace(lb(i), ub(i), 40), linspace(lb(j), ub(j), 40));
    X = repmat(mid, numel(A), 1); X(:,i) = A(:); X(:,j) = B(:);
    Z = reshape(f(X), size(A));
    nexttile; contourf(A, B, Z, 20, 'LineColor', 'none'); colorbar;
    xlabel(names{i}); ylabel(names{j});
end
sgtitle({'Response maps (surrogate)', subtitleText}, 'FontSize', 10, 'Interpreter', 'none');
exportgraphics(fig, file); close(fig);
end
