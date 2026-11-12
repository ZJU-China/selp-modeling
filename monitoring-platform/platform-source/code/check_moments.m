function check_moments()
% 验证 fiberOrientMoments 的 m2/m4 与 A4 半正定性
rng(1); hs = randn(30,3); hs = hs./sqrt(sum(hs.^2,2));

au = logspace(-4, 3, 200);
err2 = zeros(size(au)); err4 = zeros(size(au));
for k = 1:numel(au)
    a = au(k);
    Nq = 200000; u = linspace(-1,1,Nq)';
    w = exp(a*(u-1));            % 稳定归一化 exp(a*u)/exp(a)
    m2n = (u.^2)'*w./sum(w);
    m4n = (u.^4)'*w./sum(w);
    [A2v,A4v] = fiberOrientMoments(a, [0 0 1]);
    err2(k) = A2v(1,3,3) - m2n;      % A2_33 = <u^2>
    err4(k) = A4v(1,3,3) - m4n;      % A4_3333 = <u^4>
end
fprintf('max|dA2| = %e  max|dA4| = %e  @a=1e3: A2-%.6e A4-%.6e\n', ...
    max(abs(err2)), max(abs(err4)), err2(end), err4(end));

worst = 1; loc = '';
al = logspace(-4, 3, 200);
for i = 1:numel(al)
    for j = 1:size(hs,1)
        [~,A4] = fiberOrientMoments(al(i), hs(j,:));
        mineig = min(eig(squeeze(A4)));
        if mineig < worst
            worst = mineig; loc = sprintf('a=%.3g h=[%.2f %.2f %.2f]', al(i), hs(j,:));
        end
    end
end
fprintf('A4 最小特征值 = %e  @ %s\n', worst, loc);

[A2,A4] = fiberOrientMoments(0.05, [0.3 0.5 -0.8]);
fprintf('tr(A2) err = %e, A4 对称性 max = %e\n', ...
    trace(squeeze(A2(1,:,:))) - 1, ...
    max(max(abs(squeeze(A4(1,:,:))-squeeze(A4(1,:,:))')))/norm(A4(:)));

a = [1e-4 1e-2 0.5 1.5 10 1e4];
[A2,A4] = fiberOrientMoments(a, repmat([0 0 1],6,1));
fprintf('m2  = %s\n', mat2str(squeeze(A2(:,3,3))', 12));
fprintf('m4  = %s\n', mat2str(squeeze(A4(:,2,2))', 12));
end