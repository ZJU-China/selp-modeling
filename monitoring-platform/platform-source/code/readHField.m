function [Hfun, Hinfo] = readHField(file, geo)
%READHFIELD  读入磁场强度 H(x) 数据。
%  文件格式: 四列 [x(m), y(m), z(m), H(A/m)]。支持 .csv/.txt/.xlsx。
%  表头(非数值行)自动跳过; 多余列自动忽略。
%  返回:
%    Hfun  : scatteredInterpolant, 输入 Nx3 坐标 -> 输出 Nx1 的 H
%    Hinfo : 结构体, 记录数据范围/点数等, 供后处理使用
%
%  注: H(x) 为磁场强度大小 (模) |H|。若您的数据是磁通密度 B(T),
%  请先换算 H = B/mu0; 若是 mT/Gs 等单位, 请先换算成 A/m。

if nargin < 2, geo = []; end
Hinfo = struct('file', file, 'source', 'unknown', 'nPts', 0, ...
               'Hmin', [], 'Hmax', [], 'note', '');

if ~exist(file, 'file')
    error('readHField:fileNotFound', '找不到磁场数据文件: %s', file);
end

% --- 读取表格 (自动识别分隔符与表头) ---
data = readAnyTable(file);
data = data(all(isfinite(data), 2), :);      % 剔除含 NaN/Inf 的行
if size(data, 2) < 4
    error('readHField:badFormat', ...
          ['文件 %s 至少有 4 列 [x y z H], 实际检测到 %d 列。', ...
           '请检查文件格式。'], file, size(data, 2));
end

X = data(:,1); Y = data(:,2); Z = data(:,3); H = data(:,4);

% --- 去除重复坐标点 ---
[~, ia] = unique([X, Y, Z], 'rows');
X = X(ia); Y = Y(ia); Z = Z(ia); H = H(ia);

if numel(H) < 4
    error('readHField:fewPoints', '有效数据点太少, 无法插值。');
end

Hfun = scatteredInterpolant(X, Y, Z, H, 'linear', 'nearest');

Hinfo.source = 'file';
Hinfo.nPts   = numel(H);
Hinfo.Xrange = [min(X) max(X)];
Hinfo.Yrange = [min(Y) max(Y)];
Hinfo.Zrange = [min(Z) max(Z)];
Hinfo.Hmin   = min(H);
Hinfo.Hmax   = max(H);
Hinfo.note   = sprintf('interp points = %d, H range [%.3g, %.3g] A/m', ...
                       numel(H), min(H), max(H));
fprintf('[info] Read H field: %s\n', Hinfo.note);
end

% =====================================================================
function data = readAnyTable(file)
% 自动识别 .xlsx/.csv/.txt, 自动跳过表头, 自动识别分隔符。

[~, ~, ext] = fileparts(file);

% 尝试组合: readmatrix > dlmread > textscan
try
    data = readmatrix(file);
    if size(data,1) >= 1 && any(any(isfinite(data)))
        return;
    end
catch
end

try
    data = dlmread(file);
    if any(any(isfinite(data)))
        return;
    end
catch
end

% textscan: 分隔符自动检测 (逗号/分号/制表/空白)
fid = fopen(file, 'r');
if fid < 0
    error('readHField:cannotOpen', '无法打开文件: %s', file);
end
rawtxt = fread(fid, '*char').';
fclose(fid);

% 用第一行含数字的行来估计列数
lines = strsplit(rawtxt, {'\r','\n'}, 'CollapseDelimiters', true);
nCol  = 0;
for i = 1:numel(lines)
    toks = strsplit(strtrim(lines{i}));
    nNum = sum(~cellfun(@(s) isempty(s) || ~isfinite(str2double(s)), toks));
    if nNum > nCol, nCol = nNum; end
end

data = [];
for k = 1:4
    delim = {',', ';', sprintf('\t'), ' '};
    C = textscan(rawtxt, '%f', 'Delimiter', delim{k}, ...
                 'MultipleDelimsAsOne', true, 'CollectOutput', true);
    vec = C{1};
    if isempty(vec) || nCol < 1, continue; end
    nFull = floor(numel(vec) / nCol) * nCol;
    if nFull > 0
        data = reshape(vec(1:nFull), nCol, [])';
        break;
    end
end

if isempty(data)
    error('readHField:parseFail', '无法解析文件: %s', file);
end
end