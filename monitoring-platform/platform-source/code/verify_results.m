function verify_results()
clc;
S = load('results_poro_fiber.mat');
mesh = S.mesh; sol = S.sol; mat = S.mat;

nodes = mesh.nodes; u = sol.u; p = sol.p;
L = mesh.L; tol = 1e-9*max(L);

fprintf('== u 边界验证 ==\n');
z0 = abs(nodes(:,3)) < tol; sz = abs(nodes(:,1))<tol | abs(nodes(:,1)-L(1))<tol | abs(nodes(:,2))<tol | abs(nodes(:,2)-L(2))<tol;
uBot = max(abs(u(z0,:))); uSide = max(abs(u(sz,:)));
fprintf('  u@bottom max abs = %.3e m\n', uBot);
fprintf('  u@sides  max abs = %.3e m\n', uSide);

fprintf('== 孔压 (应≈0, 排水稳态) ==\n');
fprintf('  max|p| = %.3e Pa\n', max(abs(p)));

fprintf('== 顶面 sigma_zz vs 施加牵引力 ==\n');
traction_zz = S.bc.topTraction(3);
xt = abs(nodes(:,3) - L(3)) < tol;
nzE = reshape(mesh.nodes(mesh.elems,3), size(mesh.elems));
topEl = find(max(nzE, [], 2) > L(3) - tol);
szzTop = mean(sol.sigE(topEl,3));
fprintf('  施加 = %.3g Pa, 顶面单元平均 sigma_zz = %.3g Pa\n', traction_zz, szzTop);

fprintf('== 整体力平衡: 顶面反力 vs 底面反力 ==\n');
% 顶面反力 = 平均sigma_zz * 顶面积
A_top = L(1)*L(2);
F_top = szzTop * A_top;
fprintf('  F_top ~ %.3g N (期望 %.3g N)\n', F_top, traction_zz*A_top);

fprintf('== 取向张量检查 (fiberOrientMoments) ==\n');
alpha = [0; 0.1; 1; 2.2; 10; 100];
h = repmat([0 0 1], numel(alpha), 1);
[A2, A4] = fiberOrientMoments(alpha, h);
for i = 1:numel(alpha)
    A2i = squeeze(A2(i,:,:));
    fprintf('  alpha=%-6g  tr(A2)=%.6f  A4xzxx=%.2e (应为0)  A4zzzz=%.6f\n', ...
        alpha(i), trace(A2i), A4(i,5,1), A4(i,3,3));
end
errMaj = 0;
for I = 1:6, for J = 1:6
    errMaj = max(errMaj, max(abs(A4(:,I,J) - A4(:,J,I))));
end, end
fprintf('  A4 Voigt 主对称性最大偏差 = %.3e\n', errMaj);
end