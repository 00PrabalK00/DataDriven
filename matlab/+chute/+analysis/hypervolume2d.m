function [hv, spacing, front] = hypervolume2d(F, ref)
%HYPERVOLUME2D Hypervolume (minimization) of the non-dominated set of 2-objective points F (n x 2)
%w.r.t. reference point ref, and the spacing metric (std of nearest-neighbour distances on the front;
%lower = more evenly spread).
F = F(all(isfinite(F), 2) & all(F < ref, 2), :);
if isempty(F), hv = 0; spacing = NaN; front = zeros(0,2); return; end
F = sortrows(F, [1 2]);
front = F(1,:);
for i = 2:size(F,1)
    if F(i,2) < front(end,2), front(end+1,:) = F(i,:); end %#ok<AGROW>
end
hv = 0; prev2 = ref(2);
for i = 1:size(front,1)
    hv = hv + (ref(1) - front(i,1)) * (prev2 - front(i,2));
    prev2 = front(i,2);
end
if size(front,1) > 2
    d = sqrt(sum(diff(front).^2, 2)); spacing = std(d);
else
    spacing = NaN;
end
end
