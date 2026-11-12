function sol = solve3D_poroFiber(mesh, mat, bc, Hfun)
%SOLVE3D_POROFIBER  组装并求解稳态磁性纤维增强多孔弹性方程组。
%
%  未知量: 每个节点 4 个自由度 = 位移 u(3) + 孔压 p。
%  方程 (稳态):
%    (1) 积分弱形式的力平衡:
%        int B'*C(x)*B dV * u  -  G*p  =  f_traction
%    (2) 孔压稳态渗流:  int grad N' * K(x) * grad N dV * p = flux
%  因为 (2) 中不含 u (稳态), 先解 p, 再解 u, 即分块三角系统。
%
%  组装细节: 8 节点六面体, 2x2x2 高斯积分; 材料场在每个积分点
%  由 H(x) 插值得到 alpha_f(x), 再由 Fiber 分布闭式矩构造 C(x)、K(x)。

nodes = mesh.nodes; elems = mesh.elems;
NE = size(elems, 1);  NN = size(nodes, 1);
L  = mesh.L;

ndofU = 3*NN;   ndofP = NN;

% ---------------- 参考单元的 2x2x2 高斯点 ----------------
gp = [-1 1]/sqrt(3);
[g1, g2, g3] = ndgrid(gp, gp, gp);
gauss = [g1(:), g2(:), g3(:)];

Ng   = zeros(8, 8);        % Ng(g,:): 8 个形函数在 GP g 的值
dNxi = zeros(8, 3, 8);     % dNxi(a,dir,g): 形函数 a 在 GP g 对自然坐标的导数 (8x3x8)
for g = 1:8
    [Nt, dNt] = shpHex8(gauss(g,1), gauss(g,2), gauss(g,3));
    Ng(g,:)   = Nt;
    dNxi(:,:,g) = dNt;
end

Ciso  = isoStiff3D(mat.lambda_m, mat.mu_m);   % 基质各向同性刚度 6x6
cEkBT = mat.mu0*mat.mf/(mat.kB*mat.T);        % alpha_f 系数

% ---------------- 预分配稀疏组装数组 ----------------
nU = NE*576;  nP = NE*64;  nG = NE*192;
Iu = zeros(nU,1); Ju = Iu; Vu = Iu;
Ip = zeros(nP,1); Jp = Ip; Vp = Ip;
Ig = zeros(nG,1); Jg = Ig; Vg = Ig;
cu = 0; cp = 0; cg = 0;

fT = zeros(ndofU, 1);       % 表面牵引力

tol = 1e-9*max(L);

for e = 1:NE
    xe  = nodes(elems(e,:), :);              % 8x3 节点坐标
    ur0 = 3*(elems(e,:) - 1);
    dofUe = reshape([ur0+1; ur0+2; ur0+3], 24, 1);   % 位移自由度 (节点主序)
    dofPe = elems(e,:)';                             % 孔压自由度

    Kr = zeros(24); Kpr = zeros(8); Gr = zeros(24, 8);

    for g = 1:8
        Jm   = dNxi(:,:,g)' * xe;                    % 3x3 Jacobian 位移g->物理
        dNdX = dNxi(:,:,g) / Jm;                     % 8x3 dN/dx
        detJ = abs(det(Jm));
        xg   = Ng(g,:) * xe;                         % 积分点坐标 1x3

        % ---- 材料在积分点 ----
        alpha = cEkBT * Hfun(xg);
        hg    = mat.hFun(xg);
        [A2g, A4g] = fiberOrientMoments(alpha, hg);

        C  = mat.phi_m*Ciso + mat.phi_f*mat.Ef * squeeze(A4g);  % 6x6
        Km = mat.kPerp*eye(3) + (mat.kPar - mat.kPerp)*squeeze(A2g); % 3x3

        B  = buildB36(dNdX);
        Kr  = Kr  + (B'*C*B) * detJ;
        Kpr = Kpr + (dNdX*Km*dNdX') * detJ;
        Gv = zeros(24, 1);                       % 节点主序梯度 (与 dofUe 一致)
        Gv(1:3:end) = dNdX(:,1);
        Gv(2:3:end) = dNdX(:,2);
        Gv(3:3:end) = dNdX(:,3);
        Gr  = Gr  + (Gv * Ng(g,:)) * detJ;       % 24x8
    end

    % ---- 顶面牵引力 (z = Lz 面, 局部面 zeta=+1) ----
    if abs(max(xe(:,3)) - L(3)) < tol && ~isempty(bc.topTraction)
        ft = faceTraction(xe, bc.topTraction);     % 单元局部 24x1
        fT(dofUe) = fT(dofUe) + ft;                % 散播到全局
    end

    % ---- 稀疏组装 ----
    [II, JJ] = ndgrid(dofUe, dofUe);
    Iu(cu+1:cu+576) = II(:); Ju(cu+1:cu+576) = JJ(:); Vu(cu+1:cu+576) = Kr(:); cu = cu+576;

    [II, JJ] = ndgrid(dofPe, dofPe);
    Ip(cp+1:cp+64) = II(:); Jp(cp+1:cp+64) = JJ(:); Vp(cp+1:cp+64) = Kpr(:); cp = cp+64;

    [II, JJ] = ndgrid(dofUe, dofPe);
    Ig(cg+1:cg+192) = II(:); Jg(cg+1:cg+192) = JJ(:); Vg(cg+1:cg+192) = Gr(:); cg = cg+192;
end

Kuu = sparse(Iu(1:cu), Ju(1:cu), Vu(1:cu), ndofU, ndofU);
Kpp = sparse(Ip(1:cp), Jp(1:cp), Vp(1:cp), ndofP, ndofP);
G   = sparse(Ig(1:cg), Jg(1:cg), Vg(1:cg), ndofU, ndofP);

% ---------------- 边界条件: 面节点集合 ----------------
z0n = abs(nodes(:,3))            < tol;
ztn = abs(nodes(:,3) - L(3))     < tol;
x0n = abs(nodes(:,1))            < tol;
xtn = abs(nodes(:,1) - L(1))     < tol;
y0n = abs(nodes(:,2))            < tol;
ytn = abs(nodes(:,2) - L(2))     < tol;
sides = x0n | xtn | y0n | ytn;
bottom = z0n;

% ---------------- 孔压: 先解 p ----------------
fP = zeros(ndofP, 1);
% 侧面排水 (Dirichlet p = bc.pSide), 顶底面默认无渗流 (齐次 Neumann, 无组装项)
pDofs = find(sides);
if isempty(pDofs)
    warning('solve3D_poroFiber:presSingular', ...
            '孔压无 Dirichlet 边界, 系统可能奇异。建议设置 bc.pSide。');
end
if ~isempty(pDofs)
    [Kpp, fP] = penaltyBC(Kpp, fP, pDofs, bc.pSide);
end
p = Kpp \ fP;

% ---------------- 位移: 再解 u ----------------
fu = fT + G * p;                       % 孔压产生的体力项 + 表面牵引力
uFix = false(NN, 1);
if bc.fixBottom, uFix = uFix | bottom; end
if bc.fixSides,  uFix = uFix | sides;  end
fixDofs = reshape([3*(find(uFix)-1)+1; 3*(find(uFix)-1)+2; 3*(find(uFix)-1)+3], [], 1);
if ~isempty(fixDofs)
    [Kuu, fu] = penaltyBC(Kuu, fu, fixDofs, 0);
end
u = Kuu \ fu;

% ---------------- 后处理: 单元中心量与应力 ----------------
uMat = zeros(NN, 3);
uMat(:,1) = u(1:3:end); uMat(:,2) = u(2:3:end); uMat(:,3) = u(3:3:end);
pMat = full(p);

% 单元中心: 应变/应力/孔压/H/alpha/局部E_z/纤维轴向应变
xc   = zeros(NE, 3);
epsE = zeros(NE, 6);
sigE = zeros(NE, 6);
sigT = zeros(NE, 3, 3);
pE   = zeros(NE, 1);
Hc   = zeros(NE, 1);
alE  = zeros(NE, 1);
EzE  = zeros(NE, 1);      % 局部 z 方向杨氏模量 E_z = 1/S33, S = C^{-1}
epsf = zeros(NE, 1);      % 纤维轴向应变 epsf = n_i n_j eps_ij
nE   = zeros(NE, 3);      % 单元中心纤维单位方向 n = h/|h|

[N0, dN0] = shpHex8(0, 0, 0);     % 中心形函数

for e = 1:NE
    xe = nodes(elems(e,:), :);
    xc(e,:) = N0 * xe;
    Jm = dN0' * xe;
    dNdX = dN0 / Jm;
    B = buildB36(dNdX);
    ur = reshape([3*(elems(e,:)-1)+1; 3*(elems(e,:)-1)+2; 3*(elems(e,:)-1)+3], [], 1);
    epsE(e,:) = B * u(ur);
    pE(e) = N0 * pMat(elems(e,:));

    Hc(e) = Hfun(xc(e,:));
    alpha = cEkBT * Hc(e);
    hg = mat.hFun(xc(e,:));
    [~, A4g] = fiberOrientMoments(alpha, hg);
    C = mat.phi_m*Ciso + mat.phi_f*mat.Ef * squeeze(A4g);

    sigVec = C * epsE(e,:).' - pE(e) * [1 1 1 0 0 0].';
    sigE(e,:) = sigVec.';
    sigT(e,1,1) = sigVec(1); sigT(e,2,2) = sigVec(2); sigT(e,3,3) = sigVec(3);
    sigT(e,2,3) = sigVec(4); sigT(e,1,3) = sigVec(5); sigT(e,1,2) = sigVec(6);
    sigT(e,3,2) = sigVec(4); sigT(e,3,1) = sigVec(5); sigT(e,2,1) = sigVec(6);
    alE(e) = alpha;

    % ---- 局部 z 方向杨氏模量: E_z = 1/S33, S = C^{-1} ----
    S = inv(C);
    EzE(e) = 1/S(3,3);

    % ---- 纤维轴向应变: epsf = n_i n_j eps_ij ----
    nL = hg / norm(hg);                  % 纤维单位方向
    nE(e,:) = nL;
    epsf(e) = nL(1)^2*epsE(e,1) + nL(2)^2*epsE(e,2) + nL(3)^2*epsE(e,3) ...
            + nL(2)*nL(3)*epsE(e,4) + nL(1)*nL(3)*epsE(e,5) + nL(1)*nL(2)*epsE(e,6);
end

% ---------------- 汇总输出 ----------------
sol.u     = uMat;
sol.p     = pMat;
sol.xc    = xc;
sol.sigE  = sigE;      % 单元中心应力 (Voigt,Tensor 分量)
sol.sigT  = sigT;      % 单元中心应力 (3x3 张量)
sol.epsE  = epsE;
sol.pE    = pE;
sol.Hc    = Hc;
sol.alpha = alE;
sol.mat   = mat;
sol.bc    = bc;
sol.mesh  = mesh;
sol.cond  = struct('condKuu', condest(Kuu), 'condKpp', condest(Kpp));
sol.Hmin  = min(Hfun(nodes));
sol.Hmax  = max(Hfun(nodes));
sol.EzE   = EzE;      % 每单元局部 z 方向杨氏模量 (Pa)
sol.epsf  = epsf;     % 每单元纤维轴向应变 (无量纲)
sol.nE    = nE;       % 每单元纤维单位方向 n
end

% =====================================================================
function f = faceTraction(xe, traction)
% 顶面 (z=Lz, 局部 zeta=+1): 对 4 个被积表面节点施加牵引力
%  traction: 3x1 常量 (或函数句柄 @(x) 3x1, x 为表面点 1x3)
nFace = 4;
fp = [-1 1]/sqrt(3);
[f1, f2] = ndgrid(fp, fp);
fgp = [f1(:), f2(:)];
fgw = ones(nFace, 1);

centroid = mean(xe, 1);
f = zeros(24, 1);

for k = 1:nFace
    [Nf, dN] = shpHex8(fgp(k,1), fgp(k,2), 1);
    tx = xe' * dN(:,1);          % d x / d xi
    ty = xe' * dN(:,2);          % d x / d eta
    dAv = cross(tx, ty);         % 面元向量 (差符号)
    xf  = Nf * xe;               % 面点
    if dot(dAv, xf - centroid) < 0
        dAv = -dAv;
    end
    A = norm(dAv);

    if isa(traction, 'function_handle')
        t = traction(xf);
    else
        t = traction(:);
    end

    for a = 1:8
        if abs(Nf(a)) < 1e-12, continue; end
        ur = (3*(a-1) + (1:3)).';
        f(ur) = f(ur) + Nf(a) * t * A * fgw(k);   % 均为 3x1 列向量
    end
end
end

% =====================================================================
function [K, f] = penaltyBC(K, f, dofs, vals)
% 罚函数法施加 Dirichlet 边界 (保证稀疏性与对称性)
if isscalar(vals), vals = vals * ones(size(dofs)); end
nm = size(K, 1);
Kd = diag(K);
dmax = max(Kd);
if isempty(dmax) || dmax <= 0, dmax = 1; end
pen = 1e12 * dmax;
K = K + sparse(dofs, dofs, pen, nm, nm);
f(dofs) = pen .* vals(:);
end

% =====================================================================
function [N, dN] = shpHex8(xi, eta, zeta)
% 8 节点六面体三线性形函数 (参考元 [-1,1]^3)
%  N : 1x8;  dN : 8x3 = dN/d[xi eta zeta]
%  节点顺序: 1(-1,-1,-1) 2(1,-1,-1) 3(1,1,-1) 4(-1,1,-1)
%            5(-1,-1,1)  6(1,-1,1)  7(1,1,1)  8(-1,1,1)
Xn = [-1 1 1 -1 -1 1 1 -1];
Yn = [-1 -1 1 1 -1 -1 1 1];
Zn = [-1 -1 -1 -1 1 1 1 1];

N = zeros(1, 8);
dN = zeros(8, 3);
for a = 1:8
    c = 1/8;
    N(a) = c * (1 + Xn(a)*xi) * (1 + Yn(a)*eta) * (1 + Zn(a)*zeta);
    dN(a,1) = c * Xn(a) * (1 + Yn(a)*eta) * (1 + Zn(a)*zeta);
    dN(a,2) = c * (1 + Xn(a)*xi) * Yn(a) * (1 + Zn(a)*zeta);
    dN(a,3) = c * (1 + Xn(a)*xi) * (1 + Yn(a)*eta) * Zn(a);
end
end

% =====================================================================
function B = buildB36(dNdX)
% 3D 应变-位移矩阵 (6x24), 工程剪应变: eps=[e11 e22 e33 2e23 2e13 2e12]
% dNdX : 8x3, 第 a 行为节点 a 的梯度
B = zeros(6, 24);
for a = 1:8
    c = 3*(a-1);
    B(1, c+1) = dNdX(a,1);
    B(2, c+2) = dNdX(a,2);
    B(3, c+3) = dNdX(a,3);
    B(4, c+2) = dNdX(a,3);  B(4, c+3) = dNdX(a,2);
    B(5, c+1) = dNdX(a,3);  B(5, c+3) = dNdX(a,1);
    B(6, c+1) = dNdX(a,2);  B(6, c+2) = dNdX(a,1);
end
end

% =====================================================================
function C6 = isoStiff3D(lam, mu)
% 各向同性弹性张量 Voigt 形式 (6x6), 顺序 11 22 33 23 13 12
vm = [1 6 5; 6 2 4; 5 4 3];      % Voigt 下标映射
C6 = zeros(6, 6);
for i = 1:3
    for j = 1:3
        for k = 1:3
            for l = 1:3
                cijkl = lam*(i==j)*(k==l) + mu*((i==k)*(j==l) + (i==l)*(j==k));
                C6(vm(i,j), vm(k,l)) = C6(vm(i,j), vm(k,l)) + cijkl;
            end
        end
    end
end
end