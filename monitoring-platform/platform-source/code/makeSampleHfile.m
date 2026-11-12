function makeSampleHfile(file, geo)
%MAKESAMPLEHFILE  生成一个示例 H(x) 数据文件 (x,y,z,H 四列)。
%  该文件用于演示与测试; 实际计算时请替换成您的磁场数据。
%  示例场: 沿 x 方向线性增强的梯度场 H = 5e4*(1 + 0.5*x/Lx) A/m。
if nargin < 1, file = fullfile(pwd, 'H_field.csv'); end
if nargin < 2
    geo = struct('L', [0.01 0.01 0.004], 'ne', [20 20 10]);
end
geo.ne = max(geo.ne(:)', [8 8 4]);     % 至少 9x9x5 点

cx = linspace(0, geo.L(1), geo.ne(1)+1);
cy = linspace(0, geo.L(2), geo.ne(2)+1);
cz = linspace(0, geo.L(3), geo.ne(3)+1);
[X, Y, Z] = ndgrid(cx, cy, cz);

Hw = 5e4 * (1 + 0.5*X/geo.L(1));       % A/m

data = [X(:), Y(:), Z(:), Hw(:)];
writematrix(data, file);
fprintf('[信息] 已生成示例磁场文件: %s\n', file);
end