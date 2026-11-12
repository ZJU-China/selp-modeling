function out = model
%
% D.m
%
% Model exported on Sep 28 2026, 13:46 by COMSOL 6.4.0.293.

import com.comsol.model.*
import com.comsol.model.util.*

model = ModelUtil.create('Model');

model.modelPath(['D:\matlab' native2unicode(hex2dec({'7a' '0b'}), 'unicode')  native2unicode(hex2dec({'5e' '8f'}), 'unicode') ]);

model.label('B.mph');

model.param.set('r_c', '10');
model.param.set('R_c', '11');
model.param.set('h_c', '10');
model.param.set('a_c', '25');
model.param.set('b_c', '20');
model.param.set('c_c', '100');
model.param.set('aa', '1');

%% ======================= 用户参数区 =======================
%  磁场结果导出: 只导出下面这一个长方体子空间 (ROI), 其余空间一律不导出。
%
%  roiBox : 3x2, 每行一个轴 [min max], 单位 mm (与 COMSOL 几何单位 cm 不同,
%           导出时已换算)。这是"唯一被导出的子空间"。
%           它必须完整包住 run_poro_fiber.m 里的 FEM 计算域 geo.L,
%           否则 run_poro_fiber.m 会直接报错终止。
%  roiN   : 1x3, 三个方向上的采样点数, 在 roiBox 内取规则网格。
%
%  插值用的是 COMSOL 现有网格上的线性插值, 所以 ROI 处的磁场分辨率由网格
%  决定: 想要更细的场分布, 在 ROI 附近加一个 Size 节点 (网格 -> 大小) 并
%  重新求解, 而不是在这里加密导出点数。
%
%  螺线管轴线上 z=5cm 处 (线圈参数: 0.5A, 10 匝, 直径 20cm) 场最接近均匀且
%  沿 +z 方向, 因此把样品放在这里。
roiBox    = [-1.5 1.5;  -1.5 1.5;  100.5 150.5];   % mm, 3 x 3 x 1 mm
roiN      = [41 41 50];                            % 41*41*17 = 28577 点

%  导出文件设置。alpha_f = mu0*mf*H/(kB*T) 用的物理常数与
%  run_poro_fiber.m 里的 mat.mf / mat.T 保持一致。
magOut = struct( ...
    'on',      true, ...
    'dir',     'C:\Users\39309\Desktop\model\code', ...
    'magFile', 'SELP_Fe3O4_magnetic_field.csv', ...
    'roiFile', 'SELP_Fe3O4_roi_mm.csv', ...
    'mu0',     4*pi*1e-7, ...    % 真空磁导率 (T*m/A)
    'kB',      1.380649e-23, ... % 玻尔兹曼常数 (J/K)
    'T',       310, ...          % 温度 (K)
    'mf',      2.0e-18);         % 单根纤维有效磁矩 (A*m^2)
%% =========================================================

model.component.create('comp1', true);

model.component('comp1').geom.create('geom1', 3);

model.result.table.create('evl3', 'Table');

model.component('comp1').mesh.create('mesh1');

model.component('comp1').geom('geom1').lengthUnit('cm');
model.component('comp1').geom('geom1').geomRep('cadps');
model.component('comp1').geom('geom1').designBooleans(true);
model.component('comp1').geom('geom1').create('wp2', 'WorkPlane');
model.component('comp1').geom('geom1').feature('wp2').set('quickz', 'b_c');
model.component('comp1').geom('geom1').feature('wp2').set('unite', true);
model.component('comp1').geom('geom1').feature('wp2').geom.create('sq1', 'Square');
model.component('comp1').geom('geom1').feature('wp2').geom.feature('sq1').set('size', 'a_c');
model.component('comp1').geom('geom1').feature('wp2').geom.feature('sq1').set('base', 'center');
model.component('comp1').geom('geom1').feature('wp2').geom.feature('sq1').set('pos', [0 0]);
model.component('comp1').geom('geom1').create('ext2', 'Extrude');
model.component('comp1').geom('geom1').feature('ext2').setIndex('distance', 'aa', 0);
model.component('comp1').geom('geom1').feature('ext2').selection('input').set({'wp2'});
model.component('comp1').geom('geom1').create('blk1', 'Block');
model.component('comp1').geom('geom1').feature('blk1').set('size', {'c_c' 'c_c' 'c_c'});
model.component('comp1').geom('geom1').feature('blk1').set('base', 'center');
model.component('comp1').geom('geom1').feature('blk1').set('selresult', true);
model.component('comp1').geom('geom1').feature('blk1').set('selresultshow', 'all');
model.component('comp1').geom('geom1').create('hel1', 'Helix');
model.component('comp1').geom('geom1').feature('hel1').set('turns', 10);
model.component('comp1').geom('geom1').feature('hel1').set('rmaj', 'r_c');
model.component('comp1').geom('geom1').feature('hel1').set('rmin', '0.49*(R_c-r_c)');
model.component('comp1').geom('geom1').feature('hel1').set('axialpitch', 'R_c-r_c');
model.component('comp1').geom('geom1').run;
model.component('comp1').geom('geom1').run('fin');

model.component('comp1').view('view2').tag('view3');
model.component('comp1').view('view1').hideEntities.create('hide1');
model.component('comp1').view('view1').hideEntities('hide1').geom('geom1', 2);
model.component('comp1').view('view1').hideEntities('hide1').set([1 2 3 4 5 11 18]);

model.component('comp1').material.create('mat1', 'Common');
model.component('comp1').material.create('mat2', 'Common');
model.component('comp1').material('mat1').selection.set([]);
model.component('comp1').material('mat1').propertyGroup.create('Enu', 'Enu', 'Young''s modulus and Poisson''s ratio');
model.component('comp1').material('mat1').propertyGroup.create('linzRes', 'linzRes', 'Linearized resistivity');
model.component('comp1').material('mat1').selection.set([1 2 3]);
model.component('comp1').material('mat2').selection.set([1]);
model.component('comp1').material('mat2').propertyGroup('def').func.create('eta', 'Piecewise');
model.component('comp1').material('mat2').propertyGroup('def').func.create('Cp', 'Piecewise');
model.component('comp1').material('mat2').propertyGroup('def').func.create('rho', 'Analytic');
model.component('comp1').material('mat2').propertyGroup('def').func.create('k', 'Piecewise');
model.component('comp1').material('mat2').propertyGroup('def').func.create('cs', 'Analytic');
model.component('comp1').material('mat2').propertyGroup('def').func.create('an1', 'Analytic');
model.component('comp1').material('mat2').propertyGroup('def').func.create('an2', 'Analytic');
model.component('comp1').material('mat2').propertyGroup.create('RefractiveIndex', 'RefractiveIndex', 'Refractive index');
model.component('comp1').material('mat2').propertyGroup.create('NonlinearModel', 'NonlinearModel', 'Nonlinear model');
model.component('comp1').material('mat2').propertyGroup.create('idealGas', 'idealGas', 'Ideal gas');
model.component('comp1').material('mat2').propertyGroup('idealGas').func.create('Cp', 'Piecewise');

model.component('comp1').physics.create('mfco', 'MagneticFieldsCurrentsOnly', 'geom1');
model.component('comp1').physics('mfco').create('ecd1', 'ExternalCurrentDensity', 3);
model.component('comp1').physics('mfco').feature('ecd1').selection.set([2]);
model.component('comp1').physics('mfco').create('cond1', 'Conductor', 3);
model.component('comp1').physics('mfco').feature('cond1').selection.set([3]);
model.component('comp1').physics('mfco').feature('cond1').feature('term1').selection.set([14]);
model.component('comp1').physics('mfco').feature('cond1').create('gnd1', 'Ground', 2);
model.component('comp1').physics('mfco').feature('cond1').feature('gnd1').selection.set([]);

model.result.table('evl3').label('Evaluation 3D');
model.result.table('evl3').comments([native2unicode(hex2dec({'4e' 'a4'}), 'unicode')  native2unicode(hex2dec({'4e' '92'}), 'unicode')  native2unicode(hex2dec({'76' '84'}), 'unicode')  native2unicode(hex2dec({'4e' '09'}), 'unicode')  native2unicode(hex2dec({'7e' 'f4'}), 'unicode')  native2unicode(hex2dec({'50' '3c'}), 'unicode') ]);

model.component('comp1').view('view1').set('showorigin', true);
model.component('comp1').view('view1').set('showcoordinateaxes', true);
model.component('comp1').view('view3').label([native2unicode(hex2dec({'89' 'c6'}), 'unicode')  native2unicode(hex2dec({'56' 'fe'}), 'unicode') ' 3']);
model.component('comp1').view('view3').axis.set('xmin', -2.055569887161255);
model.component('comp1').view('view3').axis.set('xmax', 2.055569887161255);
model.component('comp1').view('view3').axis.set('ymin', -1.3859649896621704);
model.component('comp1').view('view3').axis.set('ymax', 1.3859649896621704);

model.component('comp1').material('mat1').label('Copper');
model.component('comp1').material('mat1').set('family', 'copper');
model.component('comp1').material('mat1').propertyGroup('def').label('Basic');
model.component('comp1').material('mat1').propertyGroup('def').set('relpermeability', {'1' '0' '0' '0' '1' '0' '0' '0' '1'});
model.component('comp1').material('mat1').propertyGroup('def').set('electricconductivity', {'5.998e7[S/m]' '0' '0' '0' '5.998e7[S/m]' '0' '0' '0' '5.998e7[S/m]'});
model.component('comp1').material('mat1').propertyGroup('def').set('thermalexpansioncoefficient', {'17e-6[1/K]' '0' '0' '0' '17e-6[1/K]' '0' '0' '0' '17e-6[1/K]'});
model.component('comp1').material('mat1').propertyGroup('def').set('heatcapacity', '385[J/(kg*K)]');
model.component('comp1').material('mat1').propertyGroup('def').set('relpermittivity', {'1' '0' '0' '0' '1' '0' '0' '0' '1'});
model.component('comp1').material('mat1').propertyGroup('def').set('density', '8960[kg/m^3]');
model.component('comp1').material('mat1').propertyGroup('def').set('thermalconductivity', {'400[W/(m*K)]' '0' '0' '0' '400[W/(m*K)]' '0' '0' '0' '400[W/(m*K)]'});
model.component('comp1').material('mat1').propertyGroup('Enu').label('Young''s modulus and Poisson''s ratio');
model.component('comp1').material('mat1').propertyGroup('Enu').set('E', '110[GPa]');
model.component('comp1').material('mat1').propertyGroup('Enu').set('nu', '0.35');
model.component('comp1').material('mat1').propertyGroup('linzRes').label('Linearized resistivity');
model.component('comp1').material('mat1').propertyGroup('linzRes').set('rho0', '1.72e-8[ohm*m]');
model.component('comp1').material('mat1').propertyGroup('linzRes').set('alpha', '0.0039[1/K]');
model.component('comp1').material('mat1').propertyGroup('linzRes').set('Tref', '298[K]');
model.component('comp1').material('mat1').propertyGroup('linzRes').addInput('temperature');
model.component('comp1').material('mat2').label('Air');
model.component('comp1').material('mat2').set('family', 'air');
model.component('comp1').material('mat2').propertyGroup('def').label('Basic');
model.component('comp1').material('mat2').propertyGroup('def').func('eta').label('Piecewise');
model.component('comp1').material('mat2').propertyGroup('def').func('eta').set('arg', 'T');
model.component('comp1').material('mat2').propertyGroup('def').func('eta').set('pieces', {'200.0' '1600.0' '-8.38278E-7+8.35717342E-8*T^1-7.69429583E-11*T^2+4.6437266E-14*T^3-1.06585607E-17*T^4'});
model.component('comp1').material('mat2').propertyGroup('def').func('eta').set('argunit', 'K');
model.component('comp1').material('mat2').propertyGroup('def').func('eta').set('fununit', 'Pa*s');
model.component('comp1').material('mat2').propertyGroup('def').func('Cp').label('Piecewise 2');
model.component('comp1').material('mat2').propertyGroup('def').func('Cp').set('arg', 'T');
model.component('comp1').material('mat2').propertyGroup('def').func('Cp').set('pieces', {'200.0' '1600.0' '1047.63657-0.372589265*T^1+9.45304214E-4*T^2-6.02409443E-7*T^3+1.2858961E-10*T^4'});
model.component('comp1').material('mat2').propertyGroup('def').func('Cp').set('argunit', 'K');
model.component('comp1').material('mat2').propertyGroup('def').func('Cp').set('fununit', 'J/(kg*K)');
model.component('comp1').material('mat2').propertyGroup('def').func('rho').label('Analytic');
model.component('comp1').material('mat2').propertyGroup('def').func('rho').set('expr', 'pA*0.02897/R_const[K*mol/J]/T');
model.component('comp1').material('mat2').propertyGroup('def').func('rho').set('args', {'pA' 'T'});
model.component('comp1').material('mat2').propertyGroup('def').func('rho').set('fununit', 'kg/m^3');
model.component('comp1').material('mat2').propertyGroup('def').func('rho').set('argunit', {'Pa' 'K'});
model.component('comp1').material('mat2').propertyGroup('def').func('rho').set('plotaxis', {'off' 'on'});
model.component('comp1').material('mat2').propertyGroup('def').func('rho').set('plotfixedvalue', {'101325' '273.15'});
model.component('comp1').material('mat2').propertyGroup('def').func('rho').set('plotargs', {'pA' '101325' '101325'; 'T' '273.15' '293.15'});
model.component('comp1').material('mat2').propertyGroup('def').func('k').label('Piecewise 3');
model.component('comp1').material('mat2').propertyGroup('def').func('k').set('arg', 'T');
model.component('comp1').material('mat2').propertyGroup('def').func('k').set('pieces', {'200.0' '1600.0' '-0.00227583562+1.15480022E-4*T^1-7.90252856E-8*T^2+4.11702505E-11*T^3-7.43864331E-15*T^4'});
model.component('comp1').material('mat2').propertyGroup('def').func('k').set('argunit', 'K');
model.component('comp1').material('mat2').propertyGroup('def').func('k').set('fununit', 'W/(m*K)');
model.component('comp1').material('mat2').propertyGroup('def').func('cs').label('Analytic 2');
model.component('comp1').material('mat2').propertyGroup('def').func('cs').set('expr', 'sqrt(1.4*R_const[K*mol/J]/0.02897*T)');
model.component('comp1').material('mat2').propertyGroup('def').func('cs').set('args', {'T'});
model.component('comp1').material('mat2').propertyGroup('def').func('cs').set('fununit', 'm/s');
model.component('comp1').material('mat2').propertyGroup('def').func('cs').set('argunit', {'K'});
model.component('comp1').material('mat2').propertyGroup('def').func('cs').set('plotfixedvalue', {'273.15'});
model.component('comp1').material('mat2').propertyGroup('def').func('cs').set('plotargs', {'T' '273.15' '373.15'});
model.component('comp1').material('mat2').propertyGroup('def').func('an1').label('Analytic 1');
model.component('comp1').material('mat2').propertyGroup('def').func('an1').set('funcname', 'alpha_p');
model.component('comp1').material('mat2').propertyGroup('def').func('an1').set('expr', '-1/rho(pA,T)*d(rho(pA,T),T)');
model.component('comp1').material('mat2').propertyGroup('def').func('an1').set('args', {'pA' 'T'});
model.component('comp1').material('mat2').propertyGroup('def').func('an1').set('fununit', '1/K');
model.component('comp1').material('mat2').propertyGroup('def').func('an1').set('argunit', {'Pa' 'K'});
model.component('comp1').material('mat2').propertyGroup('def').func('an1').set('plotaxis', {'off' 'on'});
model.component('comp1').material('mat2').propertyGroup('def').func('an1').set('plotfixedvalue', {'101325' '273.15'});
model.component('comp1').material('mat2').propertyGroup('def').func('an1').set('plotargs', {'pA' '101325' '101325'; 'T' '273.15' '373.15'});
model.component('comp1').material('mat2').propertyGroup('def').func('an2').label('Analytic 2a');
model.component('comp1').material('mat2').propertyGroup('def').func('an2').set('funcname', 'muB');
model.component('comp1').material('mat2').propertyGroup('def').func('an2').set('expr', '0.6*eta(T)');
model.component('comp1').material('mat2').propertyGroup('def').func('an2').set('args', {'T'});
model.component('comp1').material('mat2').propertyGroup('def').func('an2').set('fununit', 'Pa*s');
model.component('comp1').material('mat2').propertyGroup('def').func('an2').set('argunit', {'K'});
model.component('comp1').material('mat2').propertyGroup('def').func('an2').set('plotfixedvalue', {'200'});
model.component('comp1').material('mat2').propertyGroup('def').func('an2').set('plotargs', {'T' '200' '1600'});
model.component('comp1').material('mat2').propertyGroup('def').set('thermalexpansioncoefficient', {'alpha_p(pA,T)' '0' '0' '0' 'alpha_p(pA,T)' '0' '0' '0' 'alpha_p(pA,T)'});
model.component('comp1').material('mat2').propertyGroup('def').set('molarmass', '0.02897[kg/mol]');
model.component('comp1').material('mat2').propertyGroup('def').set('bulkviscosity', 'muB(T)');
model.component('comp1').material('mat2').propertyGroup('def').set('relpermeability', {'1' '0' '0' '0' '1' '0' '0' '0' '1'});
model.component('comp1').material('mat2').propertyGroup('def').set('relpermittivity', {'1' '0' '0' '0' '1' '0' '0' '0' '1'});
model.component('comp1').material('mat2').propertyGroup('def').set('dynamicviscosity', 'eta(T)');
model.component('comp1').material('mat2').propertyGroup('def').set('ratioofspecificheat', '1.4');
model.component('comp1').material('mat2').propertyGroup('def').set('electricconductivity', {'0[S/m]' '0' '0' '0' '0[S/m]' '0' '0' '0' '0[S/m]'});
model.component('comp1').material('mat2').propertyGroup('def').set('heatcapacity', 'Cp(T)');
model.component('comp1').material('mat2').propertyGroup('def').set('density', 'rho(pA,T)');
model.component('comp1').material('mat2').propertyGroup('def').set('thermalconductivity', {'k(T)' '0' '0' '0' 'k(T)' '0' '0' '0' 'k(T)'});
model.component('comp1').material('mat2').propertyGroup('def').set('soundspeed', 'cs(T)');
model.component('comp1').material('mat2').propertyGroup('def').addInput('temperature');
model.component('comp1').material('mat2').propertyGroup('def').addInput('pressure');
model.component('comp1').material('mat2').propertyGroup('RefractiveIndex').label('Refractive index');
model.component('comp1').material('mat2').propertyGroup('RefractiveIndex').set('n', {'1' '0' '0' '0' '1' '0' '0' '0' '1'});
model.component('comp1').material('mat2').propertyGroup('NonlinearModel').label('Nonlinear model');
model.component('comp1').material('mat2').propertyGroup('NonlinearModel').set('BA', 'def.gamma-1');
model.component('comp1').material('mat2').propertyGroup('idealGas').label('Ideal gas');
model.component('comp1').material('mat2').propertyGroup('idealGas').func('Cp').label('Piecewise 2');
model.component('comp1').material('mat2').propertyGroup('idealGas').func('Cp').set('arg', 'T');
model.component('comp1').material('mat2').propertyGroup('idealGas').func('Cp').set('pieces', {'200.0' '1600.0' '1047.63657-0.372589265*T^1+9.45304214E-4*T^2-6.02409443E-7*T^3+1.2858961E-10*T^4'});
model.component('comp1').material('mat2').propertyGroup('idealGas').func('Cp').set('argunit', 'K');
model.component('comp1').material('mat2').propertyGroup('idealGas').func('Cp').set('fununit', 'J/(kg*K)');
model.component('comp1').material('mat2').propertyGroup('idealGas').set('Rs', 'R_const/Mn');
model.component('comp1').material('mat2').propertyGroup('idealGas').set('heatcapacity', 'Cp(T)');
model.component('comp1').material('mat2').propertyGroup('idealGas').set('ratioofspecificheat', '1.4');
model.component('comp1').material('mat2').propertyGroup('idealGas').set('molarmass', '0.02897[kg/mol]');
model.component('comp1').material('mat2').propertyGroup('idealGas').addInput('temperature');
model.component('comp1').material('mat2').propertyGroup('idealGas').addInput('pressure');
model.component('comp1').material('mat2').materialType('nonSolid');

model.component('comp1').physics('mfco').feature('ecd1').set('Je', [200000; 0; 0]);
model.component('comp1').physics('mfco').feature('cond1').feature('term1').set('I0', '5[A]');
model.component('comp1').physics('mfco').feature('cond1').feature('gnd1').selection.set([1 2 3 4 5 6 7 8 9 10 13 17 18]);

model.component('comp1').mesh('mesh1').contribute('geom/detail', true);

model.study.create('std1');
model.study('std1').create('stat', 'Stationary');

model.sol.create('sol1');
model.sol('sol1').attach('std1');

model.result.create('pgB', 'PlotGroup3D');
model.result.create('pgS', 'PlotGroup3D');
model.result.create('pgBS', 'PlotGroup3D');
model.result('pgB').create('mslcB', 'Multislice');
model.result('pgS').create('strS', 'StreamlineMultislice');
model.result('pgBS').create('mslcBS', 'Multislice');
model.result('pgBS').create('strBS', 'StreamlineMultislice');
model.result.export.create('imgB', 'Image');
model.result.export.create('imgS', 'Image');
model.result.export.create('imgBS', 'Image');

model.sol('sol1').createAutoSequence('std1');

model.study('std1').runNoGen;

model.result('pgB').label('Spatial magnetic flux density |B|');
model.result('pgB').set('frametype', 'spatial');
model.result('pgB').set('showlegendsmaxmin', true);
model.result('pgB').feature('mslcB').set('multiplanexmethod', 'coord');
model.result('pgB').feature('mslcB').set('xcoord', 'mfco.CPx');
model.result('pgB').feature('mslcB').set('multiplaneymethod', 'coord');
model.result('pgB').feature('mslcB').set('ycoord', 'mfco.CPy');
model.result('pgB').feature('mslcB').set('multiplanezmethod', 'coord');
model.result('pgB').feature('mslcB').set('zcoord', 'mfco.CPz');
model.result('pgB').feature('mslcB').set('colortable', 'Prism');
model.result('pgB').feature('mslcB').set('colortabletrans', 'nonlinear');
model.result('pgB').feature('mslcB').set('colorcalibration', -0.8);
model.result('pgB').feature('mslcB').set('evaluationsettings', 'parent');
model.result('pgB').feature('mslcB').set('resolution', 'normal');
model.result('pgS').label('Magnetic field streamlines');
model.result('pgS').set('frametype', 'spatial');
model.result('pgS').feature('strS').set('multiplanexmethod', 'coord');
model.result('pgS').feature('strS').set('xcoord', 'mfco.CPx');
model.result('pgS').feature('strS').set('multiplaneymethod', 'coord');
model.result('pgS').feature('strS').set('ycoord', 'mfco.CPy');
model.result('pgS').feature('strS').set('multiplanezmethod', 'coord');
model.result('pgS').feature('strS').set('zcoord', 'mfco.CPz');
model.result('pgS').feature('strS').set('titletype', 'none');
model.result('pgS').feature('strS').set('posmethod', 'uniform');
model.result('pgS').feature('strS').set('udensity', 8);
model.result('pgS').feature('strS').set('color', 'black');
model.result('pgS').feature('strS').set('evaluationsettings', 'parent');
model.result('pgS').feature('strS').set('maxlen', 0.4);
model.result('pgS').feature('strS').set('inheritcolor', false);
model.result('pgS').feature('strS').set('resolution', 'normal');
model.result('pgBS').label('Spatial |B| with magnetic streamlines');
model.result('pgBS').set('frametype', 'spatial');
model.result('pgBS').set('showlegendsmaxmin', true);
model.result('pgBS').feature('mslcBS').set('multiplanexmethod', 'coord');
model.result('pgBS').feature('mslcBS').set('xcoord', 'mfco.CPx');
model.result('pgBS').feature('mslcBS').set('multiplaneymethod', 'coord');
model.result('pgBS').feature('mslcBS').set('ycoord', 'mfco.CPy');
model.result('pgBS').feature('mslcBS').set('multiplanezmethod', 'coord');
model.result('pgBS').feature('mslcBS').set('zcoord', 'mfco.CPz');
model.result('pgBS').feature('mslcBS').set('colortable', 'Prism');
model.result('pgBS').feature('mslcBS').set('colortabletrans', 'nonlinear');
model.result('pgBS').feature('mslcBS').set('colorcalibration', -0.8);
model.result('pgBS').feature('mslcBS').set('evaluationsettings', 'parent');
model.result('pgBS').feature('mslcBS').set('resolution', 'normal');
model.result('pgBS').feature('strBS').set('multiplanexmethod', 'coord');
model.result('pgBS').feature('strBS').set('xcoord', 'mfco.CPx');
model.result('pgBS').feature('strBS').set('multiplaneymethod', 'coord');
model.result('pgBS').feature('strBS').set('ycoord', 'mfco.CPy');
model.result('pgBS').feature('strBS').set('multiplanezmethod', 'coord');
model.result('pgBS').feature('strBS').set('zcoord', 'mfco.CPz');
model.result('pgBS').feature('strBS').set('titletype', 'none');
model.result('pgBS').feature('strBS').set('posmethod', 'uniform');
model.result('pgBS').feature('strBS').set('udensity', 8);
model.result('pgBS').feature('strBS').set('color', 'black');
model.result('pgBS').feature('strBS').set('evaluationsettings', 'parent');
model.result('pgBS').feature('strBS').set('maxlen', 0.4);
model.result('pgBS').feature('strBS').set('inheritplot', 'mslcBS');
model.result('pgBS').feature('strBS').set('inheritcolor', false);
model.result('pgBS').feature('strBS').set('resolution', 'normal');
model.result.export('imgB').set('sourceobject', 'pgB');
model.result.export('imgB').set('pngfilename', ['D:\matlab' native2unicode(hex2dec({'7a' '0b'}), 'unicode')  native2unicode(hex2dec({'5e' '8f'}), 'unicode') '\PNG\B_field.png']);
model.result.export('imgB').set('size', 'current');
model.result.export('imgB').set('unit', 'px');
model.result.export('imgB').set('height', '700');
model.result.export('imgB').set('width', '1000');
model.result.export('imgB').set('lockratio', 'off');
model.result.export('imgB').set('resolution', '150');
model.result.export('imgB').set('antialias', 'on');
model.result.export('imgB').set('zoomextents', 'on');
model.result.export('imgB').set('fontsize', '9');
model.result.export('imgB').set('colortheme', 'globaltheme');
model.result.export('imgB').set('customcolor', [1 1 1]);
model.result.export('imgB').set('background', 'color');
model.result.export('imgB').set('gltfincludelines', 'on');
model.result.export('imgB').set('title1d', 'on');
model.result.export('imgB').set('legend1d', 'off');
model.result.export('imgB').set('logo1d', 'on');
model.result.export('imgB').set('options1d', 'on');
model.result.export('imgB').set('title2d', 'on');
model.result.export('imgB').set('legend2d', 'on');
model.result.export('imgB').set('logo2d', 'on');
model.result.export('imgB').set('options2d', 'off');
model.result.export('imgB').set('title3d', 'on');
model.result.export('imgB').set('legend3d', 'on');
model.result.export('imgB').set('logo3d', 'off');
model.result.export('imgB').set('options3d', 'off');
model.result.export('imgB').set('axisorientation', 'on');
model.result.export('imgB').set('grid', 'on');
model.result.export('imgB').set('axes1d', 'on');
model.result.export('imgB').set('axes2d', 'on');
model.result.export('imgB').set('showgrid', 'on');
model.result.export('imgB').set('target', 'file');
model.result.export('imgB').set('qualitylevel', '92');
model.result.export('imgB').set('qualityactive', 'off');
model.result.export('imgB').set('imagetype', 'png');
model.result.export('imgB').set('lockview', 'off');
model.result.export('imgB').set('highprecisioncolor', 'off');
model.result.export('imgS').set('sourceobject', 'pgS');
model.result.export('imgS').set('pngfilename', ['D:\matlab' native2unicode(hex2dec({'7a' '0b'}), 'unicode')  native2unicode(hex2dec({'5e' '8f'}), 'unicode') '\PNG\B_streamline.png']);
model.result.export('imgS').set('size', 'current');
model.result.export('imgS').set('unit', 'px');
model.result.export('imgS').set('height', '700');
model.result.export('imgS').set('width', '1000');
model.result.export('imgS').set('lockratio', 'off');
model.result.export('imgS').set('resolution', '150');
model.result.export('imgS').set('antialias', 'on');
model.result.export('imgS').set('zoomextents', 'on');
model.result.export('imgS').set('fontsize', '9');
model.result.export('imgS').set('colortheme', 'globaltheme');
model.result.export('imgS').set('customcolor', [1 1 1]);
model.result.export('imgS').set('background', 'color');
model.result.export('imgS').set('gltfincludelines', 'on');
model.result.export('imgS').set('title1d', 'on');
model.result.export('imgS').set('legend1d', 'off');
model.result.export('imgS').set('logo1d', 'on');
model.result.export('imgS').set('options1d', 'on');
model.result.export('imgS').set('title2d', 'on');
model.result.export('imgS').set('legend2d', 'on');
model.result.export('imgS').set('logo2d', 'on');
model.result.export('imgS').set('options2d', 'off');
model.result.export('imgS').set('title3d', 'on');
model.result.export('imgS').set('legend3d', 'on');
model.result.export('imgS').set('logo3d', 'off');
model.result.export('imgS').set('options3d', 'off');
model.result.export('imgS').set('axisorientation', 'on');
model.result.export('imgS').set('grid', 'on');
model.result.export('imgS').set('axes1d', 'on');
model.result.export('imgS').set('axes2d', 'on');
model.result.export('imgS').set('showgrid', 'on');
model.result.export('imgS').set('target', 'file');
model.result.export('imgS').set('qualitylevel', '92');
model.result.export('imgS').set('qualityactive', 'off');
model.result.export('imgS').set('imagetype', 'png');
model.result.export('imgS').set('lockview', 'off');
model.result.export('imgS').set('highprecisioncolor', 'off');
model.result.export('imgBS').set('sourceobject', 'pgBS');
model.result.export('imgBS').set('pngfilename', ['D:\matlab' native2unicode(hex2dec({'7a' '0b'}), 'unicode')  native2unicode(hex2dec({'5e' '8f'}), 'unicode') '\PNG\B_combined.png']);
model.result.export('imgBS').set('size', 'current');
model.result.export('imgBS').set('unit', 'px');
model.result.export('imgBS').set('height', '700');
model.result.export('imgBS').set('width', '1000');
model.result.export('imgBS').set('lockratio', 'off');
model.result.export('imgBS').set('resolution', '150');
model.result.export('imgBS').set('antialias', 'on');
model.result.export('imgBS').set('zoomextents', 'on');
model.result.export('imgBS').set('fontsize', '9');
model.result.export('imgBS').set('colortheme', 'globaltheme');
model.result.export('imgBS').set('customcolor', [1 1 1]);
model.result.export('imgBS').set('background', 'color');
model.result.export('imgBS').set('gltfincludelines', 'on');
model.result.export('imgBS').set('title1d', 'on');
model.result.export('imgBS').set('legend1d', 'off');
model.result.export('imgBS').set('logo1d', 'on');
model.result.export('imgBS').set('options1d', 'on');
model.result.export('imgBS').set('title2d', 'on');
model.result.export('imgBS').set('legend2d', 'on');
model.result.export('imgBS').set('logo2d', 'on');
model.result.export('imgBS').set('options2d', 'off');
model.result.export('imgBS').set('title3d', 'on');
model.result.export('imgBS').set('legend3d', 'on');
model.result.export('imgBS').set('logo3d', 'off');
model.result.export('imgBS').set('options3d', 'off');
model.result.export('imgBS').set('axisorientation', 'on');
model.result.export('imgBS').set('grid', 'on');
model.result.export('imgBS').set('axes1d', 'on');
model.result.export('imgBS').set('axes2d', 'on');
model.result.export('imgBS').set('showgrid', 'on');
model.result.export('imgBS').set('target', 'file');
model.result.export('imgBS').set('qualitylevel', '92');
model.result.export('imgBS').set('qualityactive', 'off');
model.result.export('imgBS').set('imagetype', 'png');
model.result.export('imgBS').set('lockview', 'off');
model.result.export('imgBS').set('highprecisioncolor', 'off');
model.result.export('imgB').set('size', 'current');
model.result.export('imgB').set('unit', 'px');
model.result.export('imgB').set('height', '700');
model.result.export('imgB').set('width', '1000');
model.result.export('imgB').set('lockratio', 'off');
model.result.export('imgB').set('resolution', '150');
model.result.export('imgB').set('antialias', 'on');
model.result.export('imgB').set('zoomextents', 'on');
model.result.export('imgB').set('fontsize', '9');
model.result.export('imgB').set('colortheme', 'globaltheme');
model.result.export('imgB').set('customcolor', [1 1 1]);
model.result.export('imgB').set('background', 'color');
model.result.export('imgB').set('gltfincludelines', 'on');
model.result.export('imgB').set('title1d', 'on');
model.result.export('imgB').set('legend1d', 'off');
model.result.export('imgB').set('logo1d', 'on');
model.result.export('imgB').set('options1d', 'on');
model.result.export('imgB').set('title2d', 'on');
model.result.export('imgB').set('legend2d', 'on');
model.result.export('imgB').set('logo2d', 'on');
model.result.export('imgB').set('options2d', 'off');
model.result.export('imgB').set('title3d', 'on');
model.result.export('imgB').set('legend3d', 'on');
model.result.export('imgB').set('logo3d', 'off');
model.result.export('imgB').set('options3d', 'off');
model.result.export('imgB').set('axisorientation', 'on');
model.result.export('imgB').set('grid', 'on');
model.result.export('imgB').set('axes1d', 'on');
model.result.export('imgB').set('axes2d', 'on');
model.result.export('imgB').set('showgrid', 'on');
model.result.export('imgB').set('target', 'file');
model.result.export('imgB').set('qualitylevel', '92');
model.result.export('imgB').set('qualityactive', 'off');
model.result.export('imgB').set('imagetype', 'png');
model.result.export('imgB').set('lockview', 'off');
model.result.export('imgB').set('highprecisioncolor', 'off');
model.result.export('imgS').set('size', 'current');
model.result.export('imgS').set('unit', 'px');
model.result.export('imgS').set('height', '700');
model.result.export('imgS').set('width', '1000');
model.result.export('imgS').set('lockratio', 'off');
model.result.export('imgS').set('resolution', '150');
model.result.export('imgS').set('antialias', 'on');
model.result.export('imgS').set('zoomextents', 'on');
model.result.export('imgS').set('fontsize', '9');
model.result.export('imgS').set('colortheme', 'globaltheme');
model.result.export('imgS').set('customcolor', [1 1 1]);
model.result.export('imgS').set('background', 'color');
model.result.export('imgS').set('gltfincludelines', 'on');
model.result.export('imgS').set('title1d', 'on');
model.result.export('imgS').set('legend1d', 'off');
model.result.export('imgS').set('logo1d', 'on');
model.result.export('imgS').set('options1d', 'on');
model.result.export('imgS').set('title2d', 'on');
model.result.export('imgS').set('legend2d', 'on');
model.result.export('imgS').set('logo2d', 'on');
model.result.export('imgS').set('options2d', 'off');
model.result.export('imgS').set('title3d', 'on');
model.result.export('imgS').set('legend3d', 'on');
model.result.export('imgS').set('logo3d', 'off');
model.result.export('imgS').set('options3d', 'off');
model.result.export('imgS').set('axisorientation', 'on');
model.result.export('imgS').set('grid', 'on');
model.result.export('imgS').set('axes1d', 'on');
model.result.export('imgS').set('axes2d', 'on');
model.result.export('imgS').set('showgrid', 'on');
model.result.export('imgS').set('target', 'file');
model.result.export('imgS').set('qualitylevel', '92');
model.result.export('imgS').set('qualityactive', 'off');
model.result.export('imgS').set('imagetype', 'png');
model.result.export('imgS').set('lockview', 'off');
model.result.export('imgS').set('highprecisioncolor', 'off');
model.result.export('imgBS').set('size', 'current');
model.result.export('imgBS').set('unit', 'px');
model.result.export('imgBS').set('height', '700');
model.result.export('imgBS').set('width', '1000');
model.result.export('imgBS').set('lockratio', 'off');
model.result.export('imgBS').set('resolution', '150');
model.result.export('imgBS').set('antialias', 'on');
model.result.export('imgBS').set('zoomextents', 'on');
model.result.export('imgBS').set('fontsize', '9');
model.result.export('imgBS').set('colortheme', 'globaltheme');
model.result.export('imgBS').set('customcolor', [1 1 1]);
model.result.export('imgBS').set('background', 'color');
model.result.export('imgBS').set('gltfincludelines', 'on');
model.result.export('imgBS').set('title1d', 'on');
model.result.export('imgBS').set('legend1d', 'off');
model.result.export('imgBS').set('logo1d', 'on');
model.result.export('imgBS').set('options1d', 'on');
model.result.export('imgBS').set('title2d', 'on');
model.result.export('imgBS').set('legend2d', 'on');
model.result.export('imgBS').set('logo2d', 'on');
model.result.export('imgBS').set('options2d', 'off');
model.result.export('imgBS').set('title3d', 'on');
model.result.export('imgBS').set('legend3d', 'on');
model.result.export('imgBS').set('logo3d', 'off');
model.result.export('imgBS').set('options3d', 'off');
model.result.export('imgBS').set('axisorientation', 'on');
model.result.export('imgBS').set('grid', 'on');
model.result.export('imgBS').set('axes1d', 'on');
model.result.export('imgBS').set('axes2d', 'on');
model.result.export('imgBS').set('showgrid', 'on');
model.result.export('imgBS').set('target', 'file');
model.result.export('imgBS').set('qualitylevel', '92');
model.result.export('imgBS').set('qualityactive', 'off');
model.result.export('imgBS').set('imagetype', 'png');
model.result.export('imgBS').set('lockview', 'off');
model.result.export('imgBS').set('highprecisioncolor', 'off');
model.result.export('imgB').set('size', 'current');
model.result.export('imgB').set('unit', 'px');
model.result.export('imgB').set('height', '700');
model.result.export('imgB').set('width', '1000');
model.result.export('imgB').set('lockratio', 'off');
model.result.export('imgB').set('resolution', '150');
model.result.export('imgB').set('antialias', 'on');
model.result.export('imgB').set('zoomextents', 'on');
model.result.export('imgB').set('fontsize', '9');
model.result.export('imgB').set('colortheme', 'globaltheme');
model.result.export('imgB').set('customcolor', [1 1 1]);
model.result.export('imgB').set('background', 'color');
model.result.export('imgB').set('gltfincludelines', 'on');
model.result.export('imgB').set('title1d', 'on');
model.result.export('imgB').set('legend1d', 'off');
model.result.export('imgB').set('logo1d', 'on');
model.result.export('imgB').set('options1d', 'on');
model.result.export('imgB').set('title2d', 'on');
model.result.export('imgB').set('legend2d', 'on');
model.result.export('imgB').set('logo2d', 'on');
model.result.export('imgB').set('options2d', 'off');
model.result.export('imgB').set('title3d', 'on');
model.result.export('imgB').set('legend3d', 'on');
model.result.export('imgB').set('logo3d', 'off');
model.result.export('imgB').set('options3d', 'off');
model.result.export('imgB').set('axisorientation', 'on');
model.result.export('imgB').set('grid', 'on');
model.result.export('imgB').set('axes1d', 'on');
model.result.export('imgB').set('axes2d', 'on');
model.result.export('imgB').set('showgrid', 'on');
model.result.export('imgB').set('target', 'file');
model.result.export('imgB').set('qualitylevel', '92');
model.result.export('imgB').set('qualityactive', 'off');
model.result.export('imgB').set('imagetype', 'png');
model.result.export('imgB').set('lockview', 'off');
model.result.export('imgB').set('highprecisioncolor', 'off');
model.result.export('imgS').set('size', 'current');
model.result.export('imgS').set('unit', 'px');
model.result.export('imgS').set('height', '700');
model.result.export('imgS').set('width', '1000');
model.result.export('imgS').set('lockratio', 'off');
model.result.export('imgS').set('resolution', '150');
model.result.export('imgS').set('antialias', 'on');
model.result.export('imgS').set('zoomextents', 'on');
model.result.export('imgS').set('fontsize', '9');
model.result.export('imgS').set('colortheme', 'globaltheme');
model.result.export('imgS').set('customcolor', [1 1 1]);
model.result.export('imgS').set('background', 'color');
model.result.export('imgS').set('gltfincludelines', 'on');
model.result.export('imgS').set('title1d', 'on');
model.result.export('imgS').set('legend1d', 'off');
model.result.export('imgS').set('logo1d', 'on');
model.result.export('imgS').set('options1d', 'on');
model.result.export('imgS').set('title2d', 'on');
model.result.export('imgS').set('legend2d', 'on');
model.result.export('imgS').set('logo2d', 'on');
model.result.export('imgS').set('options2d', 'off');
model.result.export('imgS').set('title3d', 'on');
model.result.export('imgS').set('legend3d', 'on');
model.result.export('imgS').set('logo3d', 'off');
model.result.export('imgS').set('options3d', 'off');
model.result.export('imgS').set('axisorientation', 'on');
model.result.export('imgS').set('grid', 'on');
model.result.export('imgS').set('axes1d', 'on');
model.result.export('imgS').set('axes2d', 'on');
model.result.export('imgS').set('showgrid', 'on');
model.result.export('imgS').set('target', 'file');
model.result.export('imgS').set('qualitylevel', '92');
model.result.export('imgS').set('qualityactive', 'off');
model.result.export('imgS').set('imagetype', 'png');
model.result.export('imgS').set('lockview', 'off');
model.result.export('imgS').set('highprecisioncolor', 'off');
model.result.export('imgBS').set('size', 'current');
model.result.export('imgBS').set('unit', 'px');
model.result.export('imgBS').set('height', '700');
model.result.export('imgBS').set('width', '1000');
model.result.export('imgBS').set('lockratio', 'off');
model.result.export('imgBS').set('resolution', '150');
model.result.export('imgBS').set('antialias', 'on');
model.result.export('imgBS').set('zoomextents', 'on');
model.result.export('imgBS').set('fontsize', '9');
model.result.export('imgBS').set('colortheme', 'globaltheme');
model.result.export('imgBS').set('customcolor', [1 1 1]);
model.result.export('imgBS').set('background', 'color');
model.result.export('imgBS').set('gltfincludelines', 'on');
model.result.export('imgBS').set('title1d', 'on');
model.result.export('imgBS').set('legend1d', 'off');
model.result.export('imgBS').set('logo1d', 'on');
model.result.export('imgBS').set('options1d', 'on');
model.result.export('imgBS').set('title2d', 'on');
model.result.export('imgBS').set('legend2d', 'on');
model.result.export('imgBS').set('logo2d', 'on');
model.result.export('imgBS').set('options2d', 'off');
model.result.export('imgBS').set('title3d', 'on');
model.result.export('imgBS').set('legend3d', 'on');
model.result.export('imgBS').set('logo3d', 'off');
model.result.export('imgBS').set('options3d', 'off');
model.result.export('imgBS').set('axisorientation', 'on');
model.result.export('imgBS').set('grid', 'on');
model.result.export('imgBS').set('axes1d', 'on');
model.result.export('imgBS').set('axes2d', 'on');
model.result.export('imgBS').set('showgrid', 'on');
model.result.export('imgBS').set('target', 'file');
model.result.export('imgBS').set('qualitylevel', '92');
model.result.export('imgBS').set('qualityactive', 'off');
model.result.export('imgBS').set('imagetype', 'png');
model.result.export('imgBS').set('lockview', 'off');
model.result.export('imgBS').set('highprecisioncolor', 'off');

model.study('std1').createAutoSequences('all');

model.sol('sol1').runAll;

model.result('pgB').run;
model.result('pgBS').run;

model.label('B.mph');

model.result('pgBS').run;

%% =====================================================================
%  导出磁场结果 —— 只取 roiBox 定义的这一块长方体子空间
%  其它空间不评估、不导出。
%
%  输出 1: <dir>\SELP_Fe3O4_magnetic_field.csv   14 列规则网格表, 坐标 mm
%          x,y,z,Bx,By,Bz,Hx,Hy,Hz,H,hx,hy,hz,alpha_f
%          B 单位 T, H 单位 A/m, h = H/|H| 是纤维取向, alpha_f 无量纲
%  输出 2: <dir>\SELP_Fe3O4_roi_mm.csv           6 个数: xmin xmax ymin ymax zmin zmax
%  (这两个文件由 run_poro_fiber.m / readMagFromCOMSOL.m 自动读入)
%% =====================================================================
if magOut.on

    % ---------- 1. ROI 内的规则网格 (mm) ----------
    gx = linspace(roiBox(1,1), roiBox(1,2), roiN(1));
    gy = linspace(roiBox(2,1), roiBox(2,2), roiN(2));
    gz = linspace(roiBox(3,1), roiBox(3,2), roiN(3));
    [XX, YY, ZZ] = ndgrid(gx, gy, gz);
    Pmm = [XX(:), YY(:), ZZ(:)];          % N x 3, mm
    Np  = size(Pmm, 1);

    % ---------- 2. 换算到模型几何单位后逐分量插值 ----------
    Pcm = (Pmm/10).';                     % 3 x N, cm (模型 lengthUnit = cm, 1cm=10mm)
    Bv = zeros(Np, 3);
    Hv = zeros(Np, 3);
    exprB = {'mfco.Bx', 'mfco.By', 'mfco.Bz'};
    exprH = {'mfco.Hx', 'mfco.Hy', 'mfco.Hz'};
    for k = 1:3
        v = mphinterp(model, exprB{k}, 'coord', Pcm, 'unit', 'cm');
        Bv(:,k) = v(:);
    end
    try
        for k = 1:3
            v = mphinterp(model, exprH{k}, 'coord', Pcm, 'unit', 'cm');
            Hv(:,k) = v(:);
        end
    catch                                       % 若该模型未定义 H, 退回 H = B/mu0
        Hv = Bv / magOut.mu0;
    end
    if ~isequal(size(Hv), [Np 3]) || numel(Hv) ~= numel(Bv)
        error('D:magInterpSize', '磁场插值返回 %s, 期望 %s', ...
              mat2str(size(Hv)), mat2str([Np 3]));
    end

    % ---------- 3. 派生量 |H|, h = H/|H|, alpha_f ----------
    Hmag = sqrt(sum(Hv.^2, 2));
    hdir = zeros(Np, 3);
    ok   = Hmag > 0;
    hdir(ok,:)  = Hv(ok,:) ./ Hmag(ok);
    hdir(~ok,:) = repmat([0 0 1], nnz(~ok), 1);
    alphaf = magOut.mu0*magOut.mf*Hmag/(magOut.kB*magOut.T);

    if any(~isfinite(Bv(:))) || any(~isfinite(Hmag))
        warning('D:exportNonFinite', ...
                '网格点插值出现非有限值, 请确认 roiBox 完全落在几何体内部 (注意 mm 与 cm 的换算)。');
    end

    % ---------- 4. 写文件 ----------
    if ~exist(magOut.dir, 'dir'), mkdir(magOut.dir); end
    magFile = fullfile(magOut.dir, magOut.magFile);
    fid = fopen(magFile, 'w');
    if fid < 0, error('D:openMagFile', '无法写入文件: %s', magFile); end
    fprintf(fid, 'x,y,z,Bx,By,Bz,Hx,Hy,Hz,H,hx,hy,hz,alpha_f\n');
    fprintf(fid, [repmat('%.9g,', 1, 13) '%.9g\n'], ...
            [Pmm, Bv, Hv, Hmag, hdir, alphaf].');
    fclose(fid);

    roiFile = fullfile(magOut.dir, magOut.roiFile);
    fid = fopen(roiFile, 'w');
    if fid < 0, error('D:openRoiFile', '无法写入文件: %s', roiFile); end
    fprintf(fid, '%.9g %.9g %.9g %.9g %.9g %.9g\n', ...
            roiBox(1,1), roiBox(1,2), roiBox(2,1), ...
            roiBox(2,2), roiBox(3,1), roiBox(3,2));
    fclose(fid);

    % ---------- 5. 摘要 ----------
    fprintf('--------------------------------------------------------------\n');
    fprintf('[导出] 只导出了这一个长方体子空间:\n');
    fprintf('       x = [%.4g, %.4g] mm, y = [%.4g, %.4g] mm, z = [%.4g, %.4g] mm\n', ...
            roiBox(1,1), roiBox(1,2), roiBox(2,1), roiBox(2,2), roiBox(3,1), roiBox(3,2));
    fprintf('       网格 %d x %d x %d = %d 个点 (roiN 在 D.m 顶部"用户参数区"里改)\n', ...
            roiN(1), roiN(2), roiN(3), Np);
    fprintf('       |B| = [%.4g, %.4g] T,  |H| = [%.4g, %.4g] A/m\n', ...
            min(sqrt(sum(Bv.^2,2))), max(sqrt(sum(Bv.^2,2))), min(Hmag), max(Hmag));
    fprintf('       alpha_f = [%.4g, %.4g]\n', min(alphaf), max(alphaf));
    fprintf('       %s  (%d 行 x 14 列)\n', magFile, Np);
    fprintf('       %s\n', roiFile);
    fprintf('--------------------------------------------------------------\n');

end

out = model;
