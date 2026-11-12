function exportVTK(file, mesh, sol)
%EXPORTVTK  将结果写为 VTK 传统格式 (增量网格), 供 ParaView/VisIt 打开。
%  点数据: 位移向量, 孔压; 单元数据: alpha_f, sigma_zz, sigma_vm。
if nargin < 3, sol = []; end

fid = fopen(file, 'w');
fprintf(fid, '# vtk DataFile Version 3.0\n');
fprintf(fid, 'poro-fiber 3D FEM result\n');
fprintf(fid, 'ASCII\n');
fprintf(fid, 'DATASET UNSTRUCTURED_GRID\n');

nodes = mesh.nodes; elems = mesh.elems;
NN = size(nodes,1); NE = size(elems,1);

fprintf(fid, 'POINTS %d double\n', NN);
fprintf(fid, '%.15g %.15g %.15g\n', nodes.');
fprintf(fid, 'CELLS %d %d\n', NE, 9*NE);
fprintf(fid, '8 %d %d %d %d %d %d %d %d\n', elems.' - 1);
fprintf(fid, 'CELL_TYPES %d\n', NE);
fprintf(fid, '%d\n', repmat(12, NE, 1));   % 12 = VTK_HEXAHEDRON

fprintf(fid, 'POINT_DATA %d\n', NN);
fprintf(fid, 'VECTORS displacement double\n');
if ~isempty(sol) && isfield(sol,'u')
    fprintf(fid, '%.15g %.15g %.15g\n', sol.u.');
else
    fprintf(fid, '0 0 0\n');
end
fprintf(fid, 'SCALARS pore_pressure double 1\n');
fprintf(fid, 'LOOKUP_TABLE default\n');
if ~isempty(sol) && isfield(sol,'p')
    fprintf(fid, '%.15g\n', sol.p.');
else
    fprintf(fid, '0\n');
end

if ~isempty(sol) && isfield(sol,'sigE')
    fprintf(fid, 'CELL_DATA %d\n', NE);
    fprintf(fid, 'SCALARS alpha_f double 1\n');
    fprintf(fid, 'LOOKUP_TABLE default\n');
    fprintf(fid, '%.15g\n', sol.alpha.');
    fprintf(fid, 'SCALARS sigma_zz double 1\n');
    fprintf(fid, 'LOOKUP_TABLE default\n');
    fprintf(fid, '%.15g\n', sol.sigE(:,3));
    fprintf(fid, 'SCALARS von_Mises_stress double 1\n');
    fprintf(fid, 'LOOKUP_TABLE default\n');
    s = sol.sigT;
    sxx = s(:,1,1); syy = s(:,2,2); szz = s(:,3,3);
    sxy = s(:,1,2); syz = s(:,2,3); sxz = s(:,1,3);
    svm = sqrt(0.5*((sxx-syy).^2 + (syy-szz).^2 + (szz-sxx).^2 ...
          + 6*(sxy.^2 + syz.^2 + sxz.^2)));
    fprintf(fid, '%.15g\n', svm);
    fprintf(fid, 'VECTORS stress_cell double\n');
    fprintf(fid, '%.15g %.15g %.15g\n', ...
            [s(:,1,1), s(:,2,2), s(:,3,3)].');
    if isfield(sol,'epsf')
        fprintf(fid, 'SCALARS fiber_axial_strain double 1\n');
        fprintf(fid, 'LOOKUP_TABLE default\n');
        fprintf(fid, '%.15g\n', sol.epsf);
    end
    if isfield(sol,'EzE')
        fprintf(fid, 'SCALARS Ez_local double 1\n');
        fprintf(fid, 'LOOKUP_TABLE default\n');
        fprintf(fid, '%.15g\n', sol.EzE);
    end
end

fclose(fid);
end