function mesh = buildRectHexMesh(geo)
%BUILDRECTHEXMESH  在矩形块 [0,Lx]x[0,Ly]x[0,Lz] 上生成结构化六面体网格。
%  单元为 8 节点六面体 (trilinear), 节点顺序 (局部坐标):
%       1(-1,-1,-1) 2(+1,-1,-1) 3(+1,+1,-1) 4(-1,+1,-1)
%       5(-1,-1,+1) 6(+1,-1,+1) 7(+1,+1,+1) 8(-1,+1,+1)
%
%  返回:
%    mesh.nodes : NN x 3  节点坐标
%    mesh.elems : NE x 8  单元连接表 (1 基)
%    mesh.L     : 1x3 计算域尺寸
%    mesh.ne    : 1x3 各方向单元数
%    mesh.nn    : 1x3 各方向节点数

L   = geo.L;
ne  = geo.ne(:).';
nn  = ne + 1;

cx = linspace(0, L(1), nn(1));
cy = linspace(0, L(2), nn(2));
cz = linspace(0, L(3), nn(3));

% 节点编号: x 变化最快, 然后 y, 再 z
[X, Y, Z] = ndgrid(cx, cy, cz);
nodes = [X(:), Y(:), Z(:)];                       % NN x 3

% 单元编号与节点编号
nodesX = reshape(1:numel(X), nn(1), nn(2), nn(3));   % 3D 下标 -> 全局节点号

[IX, IY, IZ] = ndgrid(1:ne(1), 1:ne(2), 1:ne(3));
ix = IX(:); iy = IY(:); iz = IZ(:);                  % 各单元角标

nA = sub2ind(nn, ix,   iy,   iz);
nB = sub2ind(nn, ix+1, iy,   iz);
nC = sub2ind(nn, ix+1, iy+1, iz);
nD = sub2ind(nn, ix,   iy+1, iz);
nE = sub2ind(nn, ix,   iy,   iz+1);
nF = sub2ind(nn, ix+1, iy,   iz+1);
nG = sub2ind(nn, ix+1, iy+1, iz+1);
nH = sub2ind(nn, ix,   iy+1, iz+1);

elems = [nA nB nC nD nE nF nG nH];                  % NE x 8

mesh.nodes = nodes;
mesh.elems = elems;
mesh.L     = L;
mesh.ne    = ne;
mesh.nn    = nn;
mesh.nx    = nn(1);
mesh.ny    = nn(2);
mesh.nz    = nn(3);
end