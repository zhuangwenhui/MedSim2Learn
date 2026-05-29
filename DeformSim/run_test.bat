@echo off
set PATH=C:\Program Files (x86)\Intel\oneAPI\mkl\latest\bin;C:\Program Files (x86)\Intel\oneAPI\compiler\latest\bin;%PATH%
set SIM2LEARN_PARAM_PLY_PATH=D:\MedSim2Learn-ComplexObject\DeformSim\kidney_cgal_scaled.ply
set SIM2LEARN_PARAM_ANNOTATION_PATH=D:\MedSim2Learn-ComplexObject\DeformSim\kidney_cgal_annotation.json
set SIM2LEARN_PARAM_NUM_VECTOR=3
set SIM2LEARN_PARAM_NUM_THREADS=2
set SIM2LEARN_PARAM_MAX_OBJECTS=9
cd /d D:\MedSim2Learn-ComplexObject\DeformSim
"D:\MedSim2Learn-ComplexObject\build\DeformSim\vs2022-x64\Release\LVBasicFramework.exe"
echo === Exit code: %ERRORLEVEL% ===
