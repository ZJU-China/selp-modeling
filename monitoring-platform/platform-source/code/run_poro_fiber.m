%% =====================================================================
%  三维磁性纤维增强多孔弹性材料 —— 稳态有限元求解
%  =====================================================================
%  控制方程 (稳态, 无体力):
%    div(sigma) = 0
%    sigma_{ij} = phi_m*( lambda_m*eps_kk*delta_ij + 2*mu_m*eps_ij )
%               + phi_f*Ef*A_ijkl^ref(x)*eps_kl  -  p_w*delta_ij
%    eps_{ij}   = (1/2)*( u_{i,j} + u_{j,i} )
%    div(q)     = 0 ,   q_i = -K_ij(x) p_{w,j}
%
%  参考纤维取向 (光交联冻结):
%    rho_f*(x,n) = exp[ alpha_f(x) h_i(x) n_i ] / [ 4*pi*sinh(alpha_f)/alpha_f ]
%    alpha_f(x)  = mu0*mf*H(x) / (kB*T)
%    A_ijkl^ref(x) = int_{S2} rho_f* n_i n_j n_k n_l dOmega   (闭式解)
%
%  求解流程:
%   1) 读入 H(x) (x,y,z,H 四列表格文件), 插值到积分点计算 alpha_f
%   2) 由 Fisher 分布闭式矩构造 A2(x)、A4(x)
%   3) 先解孔压椭圆问题 div(K grad p)=0 (含孔压边界条件)
%   4) 再解线弹性平衡 K u = f_traction + G*p (含位移边界条件)
%  =====================================================================
%  使用: 直接运行本文件; 需要修改的参数集中在下面的"参数区"。
%  磁场来源: D:\matlab程序\D.m (COMSOL LiveLink) 导出的 ROI 子空间数据
%     C:\Users\39309\Desktop\model\code\SELP_Fe3O4_magnetic_field.csv
%     14 列 [x(mm) y(mm) z(mm) Bx By Bz Hx Hy Hz H hx hy hz alpha_f]
%     坐标 mm, 规则网格, 只覆盖 D.m 中 roiBox 定义的那一小块空间;
%     盒子范围同时写在 SELP_Fe3O4_roi_mm.csv, 本文件会自动读入。
%  没有该文件时可退化为本文件夹的 H_field.csv, 格式四列 [x y z H] (m, A/m)。
%  =====================================================================

clc; clear; close all;

codeDir = fileparts(mfilename('fullpath'));
if isempty(codeDir), codeDir = pwd; end
addpath(codeDir);

%% ---------------- 参数区: 材料参数 (SI 单位) ----------------
mat = struct();

mat.mu0      = 4*pi*1e-7;             % 真空磁导率 (H/m)
mat.kB       = 1.380649e-23;          % 玻尔兹曼常数 (J/K)
mat.T        = 310;                   % 环境温度 (K)
mat.mf       = 2.0e-18;               % 单根纤维有效磁矩 m_f (A*m^2)
                                      % alpha_f = mu0*mf*H/(kB*T)
mat.phi_m    = 0.30;                  % 基质体积分数 phi_m
mat.phi_f    = 0.20;                  % 纤维体积分数 phi_f
mat.lambda_m = 1.73e4;                % 基质 Lamé 常数 lambda_m (Pa)
mat.mu_m     = 7.4e3;                 % 基质 Lamé 常数 mu_m (Pa)
mat.Ef       = 1.0e5;                 % 纤维沿轴向等效模量 E_f (Pa)
mat.kPar     = 1.0e-10;               % 平行纤维取向渗透率 k_par  [m^2/(Pa*s)]
mat.kPerp    = 1.0e-11;               % 垂直纤维取向渗透率 k_perp [m^2/(Pa*s)]
mat.hDir     = [0;0;1];               % 默认磁场单位方向 h (仅当只有 H 幅值文件时使用)
                                      % 可改为函数句柄 mat.hFun (Nx3 -> Nx3)
mat.hFun     = @(x) repmat(mat.hDir(:).', size(x,1), 1);

%% ---------------- 参数区: 计算域与网格 ----------------
% FEM 域 geo.L 必须完全落在 D.m 导出的 ROI 长方体 (magROI_mm) 之内。
geo.L   = [0.0025, 0.0025, 0.005];    % 矩形域尺寸 x,y,z (m),  ≤ magROI 尺寸
geo.ne  = [20, 20, 50];                % x,y,z 方向单元数

%% ---------------- 参数区: 磁场数据 (D.m 导出的 ROI 子空间) ----------------
% 由 D:\matlab程序\D.m 输出 (COMSOL LiveLink):
%   C:\Users\39309\Desktop\model\code\SELP_Fe3O4_magnetic_field.csv
% 表头 14 列: x,y,z,Bx,By,Bz,Hx,Hy,Hz,H,hx,hy,hz,alpha_f
%   * 坐标单位 mm, 是在 D.m 的 roiBox 内取的规则网格 (不是全空间的 FEM 点)
%   * 网格尺寸 roiN 与 roiBox 都在 D.m 文件顶部的"用户参数区"里改
%   * D.m 的几何单位是 cm, 导出时已换算成 mm
roiFile  = fullfile(codeDir, 'SELP_Fe3O4_roi_mm.csv');
magCSV   = fullfile(codeDir, 'SELP_Fe3O4_magnetic_field.csv');

% 关注区域 (只使用该长方体内部的磁场), 单位 mm: [xmin xmax; ymin ymax; zmin zmax]
% 下面的值只是缺省值; 只要 D.m 输出了 roiFile, 就会自动用它的数值覆盖,
% 保证两侧盒子一致 (改 D.m 的 roiBox 时这里不用动)。
magROI_mm = [-0.25 0.25; -0.25 0.25; 50 50.5];
if exist(roiFile, 'file')
    v = readmatrix(roiFile);
    v = v(isfinite(v)).';
    if numel(v) == 6
        % 文件里是 xmin xmax ymin ymax zmin zmax, 要排成 3x2 (每行一个轴)
        magROI_mm = reshape(v(1:6), 2, 3).';
        fprintf('[信息] ROI 由 %s 自动读入: [%g %g; %g %g; %g %g] mm\n', ...
                roiFile, magROI_mm(1,1), magROI_mm(1,2), ...
                magROI_mm(2,1), magROI_mm(2,2), magROI_mm(3,1), magROI_mm(3,2));
    else
        warning('run_poro_fiber:badRoiFile', ...
            '%s 里应有 6 个数 (xmin xmax ymin ymax zmin zmax), 实际读到 %d 个, 沿用缺省 ROI。', ...
            roiFile, numel(v));
    end
end
if any(geo.L(:).' > (magROI_mm(:,2) - magROI_mm(:,1)).' * 1e-3 + 1e-12)
    error('run_poro_fiber:geoTooBig', ...
        ['geo.L = [%g %g %g] m 大于 ROI 尺寸 [%g %g %g] mm。\n' ...
         '请调小 geo.L, 或到 D.m 里把 roiBox 放大、roiN 加密后重跑。'], ...
        geo.L(1), geo.L(2), geo.L(3), ...
        (magROI_mm(1,2)-magROI_mm(1,1)), (magROI_mm(2,2)-magROI_mm(2,1)), ...
        (magROI_mm(3,2)-magROI_mm(3,1)));
end

% 若 magCSV 不存在时作演示用 (合成梯度场, 仅用于没有 COMSOL 结果的情况)
Hfile        = fullfile(codeDir, 'H_field.csv');
useSynthetic = true;

%% ---------------- 参数区: 边界条件 ----------------
bc.fixBottom  = true;                 % z=0 底面完全固定 u=0
bc.fixSides   = false;                 % 四个侧面完全固定 u=0
bc.topTraction = [0; 0; 1.0e3];       % 顶面 z=Lz 施加的牵引力 (Pa) 的三个分量
                                      % 可改为函数句柄 bc.traction = @(x) [0;0;f(x)]
bc.pSide      = 0;                    % 四个侧面的孔压 (可排水, Dirichlet), Pa
bc.pTopFlux   = 0;                    % 顶面孔压流量 q.n (Neumann, 默认0=无渗流)
bc.pBottomFlux= 0;                    % 底面同上

%% ---------------- 读入磁场, 只取 magROI 内的点 ----------------
if exist(magCSV, 'file')
    [Hfun, hfun, Hinfo] = readMagFromCOMSOL(magCSV, magROI_mm, mat.hDir, 'mm');
    mat.hFun = hfun;                  % 纤维取向: 用 D.m 导出的 hx,hy,hz 真实方向
    fprintf('[信息] %s\n', Hinfo.note);
    if any(geo.L - (Hinfo.ROI_m(:,2)-Hinfo.ROI_m(:,1)).' > 1e-9)
        warning('run_poro_fiber:geoOutsideROI', ...
            'geo.L 超出关注区域 magROI 的尺寸, 超出部分用 nearest 外推');
    end
    if Hinfo.nInROI < 0.9 * Hinfo.nTotal
        fprintf('[注意] ROI 只覆盖了导出网格的 %.1f%%, 请确认 roiBox / geo.L 设置合理\n', ...
                100 * Hinfo.nInROI / Hinfo.nTotal);
    end
elseif useSynthetic
    fprintf('[信息] 未找到 D.m 导出的磁场文件, 生成合成梯度场 H_field.csv\n');
    makeSampleHfile(Hfile, geo);
    [Hfun, Hinfo] = readHField(Hfile, geo);
else
    error('未找到磁场数据: %s (请先运行 D:\matlab程序\D.m 导出)', magCSV);
end

%% ---------------- 构建网格 ----------------
mesh = buildRectHexMesh(geo);
fprintf('[信息] 网格: 单元数=%d, 节点数=%d\n', size(mesh.elems,1), size(mesh.nodes,1));

%% ---------------- 组装并求解 ----------------
fprintf('[信息] 组装并求解 ...\n');
tic;
sol  = solve3D_poroFiber(mesh, mat, bc, Hfun);
toc;

% 峰谷 alpha 检查
alphaAll = mat.mu0*mat.mf*abs(Hfun(mesh.nodes))/(mat.kB*mat.T);
fprintf('[信息] alpha_f 范围: [%.3g, %.3g]\n', min(alphaAll), max(alphaAll));

%% ---------------- z 方向平均杨氏模量 & 纤维轴向应变 ----------------
% 每单元局部 E_z = 1/S33, S = C^{-1}(alpha(x), n(x));
% "z 方向平均杨氏模量" = 体积加权平均 (均匀网格即算术平均)
EzAll  = sol.EzE;
EzMean = mean(EzAll);
fprintf('--------------------------------------------------------------\n');
fprintf('[信息] z 方向平均杨氏模量: E_z = %.6g Pa  (= %.3f kPa = %.4g MPa)\n', ...
        EzMean, EzMean*1e-3, EzMean*1e-6);
fprintf('[信息] E_z 范围: [%.6g, %.6g] Pa  标准差: %.6g Pa\n', ...
        min(EzAll), max(EzAll), std(EzAll));

% 沿 z 分层的平均 E_z 与平均纤维轴向应变
zcU = unique(sol.xc(:,3));
fprintf('    z居中 (mm)   E_z平均 (MPa)   epsf平均 (um/m)\n');
EzZ = zeros(numel(zcU),1); epsfZ = zeros(numel(zcU),1);
for iz = 1:numel(zcU)
    sel = abs(sol.xc(:,3)-zcU(iz)) < 1e-12;
    EzZ(iz)    = mean(EzAll(sel));
    epsfZ(iz)  = mean(sol.epsf(sel));
    fprintf('    %8.4f      %10.4f       %12.4f\n', zcU(iz)*1e3, EzZ(iz)*1e-6, epsfZ(iz)*1e6);
end

% 导出每单元 & 每层的 E_z、纤维轴向应变 到 CSV
T = table(sol.xc(:,1), sol.xc(:,2), sol.xc(:,3), sol.epsf, sol.EzE, ...
          'VariableNames', {'x_m','y_m','z_m','epsf','Ez_Pa'});
Tz = table(zcU, EzZ, epsfZ, 'VariableNames', {'z_m','EzMean_Pa','epsfMean'});
writetable(T,  fullfile(codeDir,'epsf_Ez_byElement.csv'));
writetable(Tz, fullfile(codeDir,'EzZmean_byLayer.csv'));
fprintf('[信息] 已导出: epsf_Ez_byElement.csv (每单元), EzZmean_byLayer.csv (每层均值)\n');
fprintf('--------------------------------------------------------------\n');

%% ---------------- 后处理与输出 ----------------
plotResults(mesh, sol, Hfun, Hinfo, mat, geo);

outFile = fullfile(codeDir, 'results_poro_fiber.mat');
save(outFile, 'mesh', 'sol', 'Hinfo', 'mat', 'geo', 'bc');
fprintf('[信息] 结果已保存: %s\n', outFile);

try
    exportVTK(fullfile(codeDir,'poro_fiber_result.vtk'), mesh, sol);
    fprintf('[信息] VTK 结果已写出: %s (可用 ParaView 打开)\n', ...
            fullfile(codeDir,'poro_fiber_result.vtk'));
catch ME
    warning('VTK 输出失败: %s', ME.message);
end