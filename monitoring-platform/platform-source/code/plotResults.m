function plotResults(mesh, sol, Hfun, Hinfo, mat, geo)
%PLOTRESULTS  Visualization of displacement / pore pressure / stress / H / epsf / Ez fields.
%
%   Typesetting convention: export resolution is 150 dpi, so the canvas must be
%   large enough and the font sizes large enough, otherwise long titles and an
%   unlabeled colorbar are squeezed together (previously the default figure
%   size was about 730 px, title used the 12 pt default, and the colorbar had
%   no unit label, making annotations almost unreadable after export).
%   Every figure is uniform: explicit canvas size, three font sizes, colorbar
%   with units, and the title split into a "quantity + statistics" pair.

if nargin < 6, geo = []; end
if nargin < 5 || isempty(mat), mat = struct(); end

nodes = mesh.nodes;
u     = sol.u;
p     = sol.p;
xc    = sol.xc;

umag = sqrt(sum(u.^2, 2));
Hn   = Hfun(nodes);

% ---------- shared plotting parameters ----------
FIG_POS  = [80 80 1180 880];   % px, keeps things legible at 150 dpi
FS_AX    = 13;                 % axis label size
FS_TITLE = 15;                 % main title size
FS_SUB   = 12;                 % second title line (statistics)
FS_CB    = 12;                 % colorbar tick and label size
FS_NOTE  = 11;                 % bottom note size

newFig = @(nm) figure('Name', nm, 'Position', FIG_POS, 'Color', 'w');

% tighten the gap between the axes and the colorbar so the colorbar does not overlap the plot
AX_POS = [0.085 0.115 0.76 0.74];
CB_POS = [0.875 0.115 0.022 0.74];

%% ---------- Figure 1: displacement field (nodal cloud) ----------
h = newFig('Displacement_field');
scatter3(nodes(:,1)*1e3, nodes(:,2)*1e3, nodes(:,3)*1e3, 8, umag*1e6, 'filled');
colormap(jet(256));
cb = colorbar; set(cb, 'FontSize', FS_CB);
set(cb, 'Position', CB_POS);
cax = findobj(h, 'Type', 'axes'); set(cax, 'Position', AX_POS);
axis equal; grid on; box on;
set(gca, 'FontSize', FS_AX);
xlabel('x (mm)'); ylabel('y (mm)'); zlabel('z (mm)');
title({sprintf('Nodal displacement |\\itu\\rm|', 0), ...
       sprintf('Unit \\mum,  max = %.4g \\mum', max(umag)*1e6)}, ...
      'FontSize', FS_TITLE, 'FontWeight', 'bold');
cb.Label.String = '|\itu\rm| (\mum)';

% Deformed overlay
scale = 0.05 * max(mesh.L) / max(umag + eps);
def   = nodes + scale * u;
hold on;
quiver3(nodes(:,1)*1e3, nodes(:,2)*1e3, nodes(:,3)*1e3, ...
        u(:,1)*1e6, u(:,2)*1e6, u(:,3)*1e6, 0, 'color', [0.4 0.4 0.4], 'LineWidth', 0.3);
% Deformed top contour
ztol = max(mesh.L)*1e-9;
top = abs(nodes(:,3) - mesh.L(3)) < ztol;
plot3(def(top,1)*1e3, def(top,2)*1e3, def(top,3)*1e3, 'k.', 'MarkerSize', 2);
hold off;
view(3);

%% ---------- Figure 2: pore pressure field ----------
h = newFig('Pore_pressure');
scatter3(nodes(:,1)*1e3, nodes(:,2)*1e3, nodes(:,3)*1e3, 8, p, 'filled');
colormap(jet(256));
cb = colorbar; set(cb, 'FontSize', FS_CB);
set(cb, 'Position', CB_POS);
cax = findobj(h, 'Type', 'axes'); set(cax, 'Position', AX_POS);
axis equal; grid on; box on;
set(gca, 'FontSize', FS_AX);
xlabel('x (mm)'); ylabel('y (mm)'); zlabel('z (mm)');
if max(abs(p)) > 0
    title({sprintf('Pore water pressure p_w', 0), ...
           sprintf('Unit Pa,  max|p| = %.4g Pa', max(abs(p)))}, ...
          'FontSize', FS_TITLE, 'FontWeight', 'bold');
else
    title({'Pore water pressure p_w', 'No fluid load in this case, p \\equiv 0 (Pa)'}, ...
          'FontSize', FS_TITLE, 'FontWeight', 'bold');
end
cb.Label.String = 'p_w (Pa)';
view(3);

%% ---------- Figure 3: element-center sigma_zz ----------
h = newFig('Stress_sigma_zz');
szz = sol.sigE(:,3);
scatter3(xc(:,1)*1e3, xc(:,2)*1e3, xc(:,3)*1e3, 10, szz*1e-3, 'filled');
colormap(jet(256));
cb = colorbar; set(cb, 'FontSize', FS_CB);
set(cb, 'Position', CB_POS);
cax = findobj(h, 'Type', 'axes'); set(cax, 'Position', AX_POS);
axis equal; grid on; box on;
set(gca, 'FontSize', FS_AX);
xlabel('x (mm)'); ylabel('y (mm)'); zlabel('z (mm)');
title({sprintf('Element-center axial stress \\sigma_{zz}', 0), ...
       sprintf('Unit kPa,  \\range = [%.4g, %.4g] kPa', min(szz)*1e-3, max(szz)*1e-3)}, ...
      'FontSize', FS_TITLE, 'FontWeight', 'bold');
cb.Label.String = '\sigma_{zz} (kPa)';
view(3);

%% ---------- Figure 4: H field ----------
h = newFig('Magnetic_field_H(x)');
scatter3(nodes(:,1)*1e3, nodes(:,2)*1e3, nodes(:,3)*1e3, 6, Hn, 'filled');
colormap(jet(256));
cb = colorbar; set(cb, 'FontSize', FS_CB);
set(cb, 'Position', CB_POS);
cax = findobj(h, 'Type', 'axes'); set(cax, 'Position', AX_POS);
axis equal; grid on; box on;
set(gca, 'FontSize', FS_AX);
xlabel('x (mm)'); ylabel('y (mm)'); zlabel('z (mm)');
title({sprintf('Applied magnetic field H(x)', 0), ...
       sprintf('Unit A/m,  H\\in[%.4g, %.4g] A/m', min(Hn), max(Hn))}, ...
      'FontSize', FS_TITLE, 'FontWeight', 'bold');
cb.Label.String = 'H (A/m)';
view(3);

%% ---------- Figure 5: fiber axial strain epsf = n_i n_j eps_ij ----------
h = newFig('Fiber_axial_strain_epsf');
if isfield(sol,'epsf') && ~isempty(sol.epsf)
    ef = sol.epsf;
    scatter3(xc(:,1)*1e3, xc(:,2)*1e3, xc(:,3)*1e3, 10, ef*1e6, 'filled');
    colormap(jet(256));
    cb = colorbar; set(cb, 'FontSize', FS_CB);
    set(cb, 'Position', CB_POS);
    cax = findobj(h, 'Type', 'axes'); set(cax, 'Position', AX_POS);
    axis equal; grid on; box on;
    set(gca, 'FontSize', FS_AX);
    xlabel('x (mm)'); ylabel('y (mm)'); zlabel('z (mm)');
    title({sprintf('Fiber axial strain \\epsilon_f = n_i n_j \\epsilon_{ij}', 0), ...
           sprintf('Unit \\mum/m,  \\range = [%.4g, %.4g]', min(ef)*1e6, max(ef)*1e6)}, ...
          'FontSize', FS_TITLE, 'FontWeight', 'bold');
    cb.Label.String = '\epsilon_f (\mum/m)';
else
    set(gca, 'FontSize', FS_AX);
    text(0.5, 0.5, 'compute epsf first', 'HorizontalAlignment', 'center', 'FontSize', FS_SUB);
end
view(3);

%% ---------- Figure 6: local z-direction Young's modulus ----------
h = newFig('Local_axial_modulus_E_z');
if isfield(sol,'EzE') && ~isempty(sol.EzE)
    Ez = sol.EzE;
    scatter3(xc(:,1)*1e3, xc(:,2)*1e3, xc(:,3)*1e3, 10, Ez*1e-6, 'filled');
    colormap(jet(256));
    cb = colorbar; set(cb, 'FontSize', FS_CB);
    set(cb, 'Position', CB_POS);
    cax = findobj(h, 'Type', 'axes'); set(cax, 'Position', AX_POS);
    axis equal; grid on; box on;
    set(gca, 'FontSize', FS_AX);
    xlabel('x (mm)'); ylabel('y (mm)'); zlabel('z (mm)');
    title({sprintf('Local axial modulus E_z', 0), ...
           sprintf('Unit MPa,  mean %.4g,  \\range = [%.4g, %.4g]', ...
                   mean(Ez)*1e-6, min(Ez)*1e-6, max(Ez)*1e-6)}, ...
          'FontSize', FS_TITLE, 'FontWeight', 'bold');
    cb.Label.String = 'E_z (MPa)';
else
    set(gca, 'FontSize', FS_AX);
    text(0.5, 0.5, 'compute E_z first', 'HorizontalAlignment', 'center', 'FontSize', FS_SUB);
end
view(3);

% ---------- bottom source note (leave enough height to clear the xlabel) ----------
if ~isempty(Hinfo) && isfield(Hinfo,'note') && ~isempty(Hinfo.note)
    for f = findobj('Type', 'figure')
        annotation(f, 'textbox', [0.085 0.012 0.80 0.055], ...
                   'String', Hinfo.note, 'EdgeColor', 'none', ...
                   'HorizontalAlignment', 'center', 'FontSize', FS_NOTE, ...
                   'Interpreter', 'none');
    end
end

% ---------- 保存图片 (批处理下窗口不可见) ----------
out = fullfile(fileparts(mfilename('fullpath')), 'figures');
if exist(out, 'dir') ~= 7, mkdir(out); end
figs = findobj('Type', 'figure');
for i = 1:numel(figs)
    nm = get(figs(i), 'Name');
    if isempty(nm), nm = sprintf('fig%02d', i); end
    nm = regexprep(nm, '[\\/:*?"<>|\s]', '_');
    exportgraphics(figs(i), fullfile(out, [nm '.png']), 'Resolution', 150);
end
end
