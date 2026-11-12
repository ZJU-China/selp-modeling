function [Hfun, hfun, info] = readMagFromCOMSOL(csvFile, ROI_mm, fallbackDir, coordUnit)
%READMAGFROMCOMSOL  读取 D.m (COMSOL LiveLink) 导出的磁场表,
%                   只保留"关注区域" ROI 内的点, 建立插值函数。
%
%  输入:
%     csvFile    : D.m 输出路径
%                  (C:\Users\39309\Desktop\model\code\SELP_Fe3O4_magnetic_field.csv)
%                  表头 14 列: x,y,z,Bx,By,Bz,Hx,Hy,Hz,H,hx,hy,hz,alpha_f
%                  坐标已在 D.m 里换算成 mm, 是 roiBox 内的规则网格。
%     ROI_mm     : 关注的长方体区域 [xmin xmax; ymin ymax; zmin zmax], 单位 mm。
%                  FEM 计算域(=geo.L, 单位 m) 必须落在该 box 内。
%                  建议直接用 D.m 一起输出的 SELP_Fe3O4_roi_mm.csv 里的数值。
%     fallbackDir: 可选, 在 H≈0 处使用的单位方向 (默认 [0 0 1])。
%     coordUnit  : 可选, CSV 坐标单位 'mm'(默认) / 'm' / 'auto'。
%
%  输出:
%     Hfun  : @(xq) 返回 H (A/m)。xq 为 FEM 局部坐标 (m, 以 ROI 最小角为原点)。
%     hfun  : @(xq) 返回纤维单位方向 n (Nx3), 由导出的 hx,hy,hz 插值并归一化。
%     info  : struct, 含点数统计、裁剪范围、H 范围等。
%
%  坐标约定:
%    * 局部 FEM 坐标 -> 全局 COMSOL 坐标:  x_global = ROI最小角 + xq (m)。

if nargin < 3, fallbackDir = [0 0 1]; end
fallbackDir = fallbackDir(:).' / norm(fallbackDir(:));
if nargin < 4 || isempty(coordUnit), coordUnit = 'mm'; end

T = readtable(csvFile, 'VariableNamingRule', 'preserve');

% ---- 坐标单位识别 ----
c = [T.x(:), T.y(:), T.z(:)];
switch lower(char(coordUnit))
    case 'mm'
        scale = 1e-3;                    % D.m 导出的就是 mm
    case 'm'
        scale = 1;
    otherwise                            % 'auto'
        if max(max(abs(c))) > 0.5
            scale = 1e-3;                % 视为 mm
        else
            scale = 1;                   % 已为 m
        end
end
c = c * scale;

% ---- 裁剪 ROI (mm -> m) ----
RO = ROI_mm * 1e-3;
dataBox = [min(c); max(c)];          % 2x3 = [min; max]
% ROI 若超出数据覆盖范围则收缩并提示
clamped = false;
for k = 1:3
    if RO(k,1) < dataBox(1,k)
        RO(k,1) = dataBox(1,k); clamped = true;
    end
    if RO(k,2) > dataBox(2,k)
        RO(k,2) = dataBox(2,k); clamped = true;
    end
end
if clamped
    warning('readMagFromCOMSOL:clipROI', ...
        'ROI 超出磁场数据覆盖范围, 已自动收缩为 [%.4f %.4f; %.4f %.4f; %.4f %.4f] m', ...
        RO(1,1),RO(1,2),RO(2,1),RO(2,2),RO(3,1),RO(3,2));
end

sel = c(:,1) >= RO(1,1) & c(:,1) <= RO(1,2) ...
    & c(:,2) >= RO(2,1) & c(:,2) <= RO(2,2) ...
    & c(:,3) >= RO(3,1) & c(:,3) <= RO(3,2);

if nnz(sel) < 27
    error('readMagFromCOMSOL:fewPoints', ...
        'ROI 内仅 %d 个磁场数据点, 不足以建立三维插值。请检查 ROI_mm 或网格密度。', nnz(sel));
end

xs = c(sel,1); ys = c(sel,2); zs = c(sel,3);
Hs = T.H(sel); hxs = T.hx(sel); hys = T.hy(sel); hzs = T.hz(sel);

% ---- 插值器 (线性 + nearest 外推) ----
F.H  = scatteredInterpolant(xs, ys, zs, Hs,  'linear', 'nearest');
F.hx = scatteredInterpolant(xs, ys, zs, hxs, 'linear', 'nearest');
F.hy = scatteredInterpolant(xs, ys, zs, hys, 'linear', 'nearest');
F.hz = scatteredInterpolant(xs, ys, zs, hzs, 'linear', 'nearest');

% ---- 建立句柄: 局部坐标 -> 全局坐标查表 ----
shift = RO(:,1).';                 % ROI 最小角 (m)
Hfun  = @(xq) F.H( shift(1) + xq(:,1), shift(2) + xq(:,2), shift(3) + xq(:,3) );
hfun  = @(xq) interpH(xq, F, shift, fallbackDir);

% ---- 统计信息 ----
info.scale      = scale;
info.nTotal     = height(T);
info.nInROI     = nnz(sel);
info.ROI_m      = RO;
info.dataBox_m  = dataBox;
info.HrangeInROI= [min(Hs), max(Hs)];
info.fallbackDir= fallbackDir;
info.note       = sprintf('COMSOL field interpolation: %d points in ROI, H in [%.3g, %.3g] A/m', ...
                          info.nInROI, info.HrangeInROI(1), info.HrangeInROI(2));
end

% =====================================================================
function nq = interpH(xq, F, shift, fallbackDir)
q = shift + xq;                   % 局部 -> 全局
vx = F.hx(q(:,1), q(:,2), q(:,3));
vy = F.hy(q(:,1), q(:,2), q(:,3));
vz = F.hz(q(:,1), q(:,2), q(:,3));
nm = sqrt(vx.^2 + vy.^2 + vz.^2);
nq = zeros(size(xq));
ok = nm > 1e-12;
nq(ok,1) = vx(ok)./nm(ok);
nq(ok,2) = vy(ok)./nm(ok);
nq(ok,3) = vz(ok)./nm(ok);
nq(~ok,:) = repmat(fallbackDir, nnz(~ok), 1);
end