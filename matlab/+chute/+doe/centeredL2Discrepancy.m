function cd2 = centeredL2Discrepancy(X)
%CENTEREDL2DISCREPANCY Centered L2 discrepancy of points in [0,1]^d (lower = more uniform coverage).
[n, d] = size(X);
a = abs(X - 0.5);
t1 = (13/12)^d;
t2 = 2/n * sum(prod(1 + 0.5*a - 0.5*a.^2, 2));
s = 0;
for i = 1:n
    s = s + sum(prod(1 + 0.5*a(i,:) + 0.5*a - 0.5*abs(X(i,:) - X), 2));
end
cd2 = sqrt(t1 - t2 + s / n^2);
end
