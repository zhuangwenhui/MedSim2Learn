# Sim2VFP: Simulation to Vision-Force Pair Processor

基于sim2vfp.py(1686行)和load_optimizer.py(1177行)实际代码的完整文档

这个工具提供了完整的工作流程，包括3D网格`.ply`文件渲染、相机视角预览、智能负载优化，以及生成配对的视觉-力向量`.pt`文件供深度学习使用。

## 📂 Folder Structure (Default)

```
Sim2Learn/
├── DKNet/                            # Deep learning training framework
├── Obj_post/                         # This directory (data processing)
│   ├── sim2vfp.py                    # Main script for vision-force processing (1686行)
│   ├── load_optimizer.py             # 智能CPU负载优化器 (1177行) 【新增】
│   ├── cameraSetupTest/              # Camera preview & configuration storage
│   │   ├── plate.ply                 # Default preview model
│   │   └── camera_config_*.json      # Saved camera views (up to 5)
│   ├── Ori_deformation/              # Input simulation datasets
│   │   ├── DeformedSampleDec_v1/     # Dataset with 43,500 .ply files + CSV
│   │   ├── DeformedSampleJul_v1_Center/  # Dataset with 45,000 .ply files + CSV 【新增】
│   │   └── DeformedSampleMar_v1/
│   ├── Ren_png/                      # Rendered output images (.png format)
│   ├── render_errors/                # Error logs from rendering process
│   │   └── error_log.csv             # Records of any rendering failures
│   ├── preprocessed_data/            # Base directory for serialized outputs
│   ├── preprocessed_data_224_DataNorm_FN/    # Dataset-norm with force-norm (224×224)
│   ├── preprocessed_data_224_DataNorm_NFN/   # Dataset-norm without force-norm (224×224)
│   └── optimization_results_*.png    # CPU优化可视化图表 【新增】
└── Obj_pre/                          # Pre-processing & mesh generation tools
```

---

## ⚙️ Installation

```bash
# Core dependencies for sim2vfp.py
pip install open3d numpy pandas pillow tqdm torch

# Additional dependencies for load_optimizer.py
pip install psutil matplotlib  # matplotlib is optional for visualization
```

---

## 🏗️ Core Architecture (实际代码结构)

### sim2vfp.py 主要类 (行1-1686) - 企业级多模式架构
```python
CaptureConfig        # 配置管理类 (行19-31)
CameraManager        # 相机视角管理和存储 (行33-229)
Renderer            # 并行PLY→PNG渲染引擎 (行231-382)
DataPreprocessor    # 异步数据序列化器 (行384-1024) - 企业级异步架构
Sim2VFP             # 主要工作流编排器 (行1025-1462)
DataVisualizer      # 数据验证和可视化工具 (行1416-1678)
```

### load_optimizer.py 优化工具 (行1-1177)
```python
DatasetAnalyzer          # 数据集分析和自适应采样 (行59-150)
CoreHardwareProfiler     # 跨平台硬件检测 (行153-507)
FastLoadOptimizer        # 二分搜索优化算法 (行633-830)
IntelligentLoadOptimizer # 主要优化协调器 (行832-1049)
OptimizationVisualizer   # 结果可视化生成器 (行509-631)
```

---

## Known Issues

- Robust Percentile归一化方法 (选项4) 当前在元数据生成方面存在问题，建议暂时避免使用直到未来版本修复。
- 容器环境下GUI预览功能受限，建议使用headless模式或load_optimizer.py进行优化。

## Usage Summary

### 0. 【新增】智能负载优化 (推荐首先运行)
```bash
# 硬件分析
python load_optimizer.py --profile

# 数据集优化分析
python load_optimizer.py --ply-dir Ori_deformation/DeformedSampleJul_v1_Center

# 保存优化配置到JSON
python load_optimizer.py --ply-dir [DATASET_PATH] --save-config optimal_load.json

# 禁用可视化图表生成
python load_optimizer.py --ply-dir [DATASET_PATH] --no-plot

# 自定义精度阈值 (默认5%)
python load_optimizer.py --ply-dir [DATASET_PATH] --precision 3
```

### 1. Preview Camera View (Default Mode)
```bash
python sim2vfp.py --preview --preview-mode default
```
Preview `plate.ply` and optionally save camera view to `cameraSetupTest/`.

### 2. Preview Camera View (Instance Mode)
```bash
python sim2vfp.py --preview --preview-mode instance
```
Preview a random `.ply` from a chosen dataset for customized view setup.

### 3. List All Saved Camera Views
```bash
python sim2vfp.py --list-cameras
```
Prints available `camera_config_*.json` files in `cameraSetupTest/`.

### 4. Batch Render `.ply` to `.png` (Parallel)
```bash
python sim2vfp.py --parallel
```
Interactive rendering workflow with dataset and view selection.

**重要**: CPU负载选项只支持两个固定值 (实际代码限制):
```bash
python sim2vfp.py --parallel --load 50   # 50% CPU负载
python sim2vfp.py --parallel --load 75   # 75% CPU负载 (默认)
```

### 5. Serialize Rendered PNG + Force CSV to `.pt`
```bash
python sim2vfp.py --serialize
```
Interactive dataset selection with enhanced options for:
- Image resizing (224×224×C, 256×256×C, or 512×512×C)
- Multiple normalization strategies:
  - None (only scale to [0,1] range)
  - ImageNet standard normalization
  - Dataset-specific normalization (calculated from your data) - *Recommended*
  - Grayscale-optimized normalization (for grayscale/rendered images)
  - Robust percentile-based normalization (⚠️ currently has issues)
- Force data normalization with customizable scaling factors

### 6. Visualize Serialized Data
```bash
python sim2vfp.py --visualize
```
Interactive visualization of serialized data with options to:
- Browse all available preprocessed datasets
- View sample images with their force data
- Compare different batch samples
- Show random samples
- Display dataset metadata summary

### 7. Full Pipeline: Render + Serialize
```bash
python sim2vfp.py --pipeline
```
Run rendering and serialization in one integrated workflow.

### 8. Programmatic API Usage
```python
from sim2vfp import Sim2VFP

processor = Sim2VFP()

# Full pipeline with interactive steps:
processor.run_pipeline()

# Or configure each step explicitly:
processor.use_dataset("/path/to/dataset") \
         .use_camera("/path/to/camera.json") \
         .set_output_png_dir("/path/to/png/output") \
         .render(max_workers=4) \
         .set_output_data_dir("/path/to/data/output") \
         .configure_serialization(
             do_resize=True,
             target_size=(224, 224),
             normalize_images=True,
             normalize_forces=True,
             force_normalization={'x_scale': 1, 'y_scale': 1, 'z_scale': 10}
         ) \
         .serialize()
```

---

## Normalization Options

### Image Normalization Strategies

1. **None (Option 0)**
   - Simply scales pixel values to [0,1] range
   - Preserves original brightness and contrast relationships
   - Directory suffix: `NoNorm`

2. **ImageNet Standard (Option 1)**
   - Uses the ImageNet mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]
   - Good for transfer learning with pre-trained models
   - Directory suffix: `ImgNetNorm`

3. **Dataset-specific (Option 2)** - *Recommended for general use*
   - Calculates mean and standard deviation from your dataset
   - Samples up to 1000 images for statistics calculation
   - Directory suffix: `DataNorm`

4. **Grayscale-optimized (Option 3)**
   - Uses single mean/std for all channels
   - Good for rendered images
   - Directory suffix: `GrayNorm`

**Note**: Only 4 normalization strategies are implemented in the actual code

### Force Data Normalization

When enabled, allows separate scaling factors for each dimension:
- X-axis normalization scale: divide by specified value
- Y-axis normalization scale: divide by specified value
- Z-axis normalization scale: divide by specified value

Common configurations:
- Equal normalization (1:1:1): all axes scaled equally
- Z-emphasized normalization (1:1:10): when Z-axis has larger magnitude

Directory suffix: `FN` (with force normalization) or `NFN` (without)

---

## Output Example
Serialized files will be saved in named directories following the convention:
```
preprocessed_data_SIZE_NORMTYPE_FORCENORM/
```

For example:
```
preprocessed_data_224_DataNorm_NFN/    # 224×224, dataset normalization, no force norm
preprocessed_data_224_DataNorm_FN/     # 224×224, dataset normalization, with force norm
```

Each directory contains:
```
preprocessed_data_224_DataNorm_FN/
├── preprocessed_batch_0000.pt
├── preprocessed_batch_0001.pt
├── ...
└── metadata.yaml                      # Contains normalization parameters and dataset info
```

Each `.pt` file contains a batch of dictionaries:
```python
{
    "id": "deformed_00001",
    "image": torch.Tensor,      # shape (C, H, W)
    "force": torch.Tensor       # shape (3,) [fx, fy, fz]
}
```

The `metadata.yaml` file includes:
- Image normalization parameters (mean, std, or percentiles)
- Force normalization scale values (if enabled)
- Original and resized image dimensions
- Processing date and time
- Total samples and batch information

The serialized data in `Obj_post/preprocessed_data_224_*` directories is designed to be used with the DKNet training framework located in the DKNet directory. This integration allows for a complete simulation-to-learning pipeline.

---

## Performance Metrics (基于实际测试)

### sim2vfp.py 性能指标
- **Rendering**: ~72 images/second with 24 processes
- **Serialization**: ~500 samples/second (async processing)
- **Memory Usage**: 1740 samples per batch, 200 samples per chunk
- **CPU Load Options**: 1-100% (any percentage supported)

### load_optimizer.py 优化性能
- **硬件检测**: <3秒 (跨平台支持Linux/Windows/macOS)
- **数据集扫描**: 自适应采样，大型数据集(>50K文件)使用30%采样率
- **优化测试**: 2-8次测试 (二分搜索，取决于精度阈值)
- **可视化生成**: <1秒 (matplotlib高分辨率图表)
- **总优化时间**: 通常<5分钟 (包含采样、测试、可视化)

---

## Development Notes

### sim2vfp.py 技术特性
- 6类架构设计 (1686行代码)
- 方法链式调用支持
- 异步序列化处理
- 多进程渲染
- 4种图像归一化策略
- 完整元数据生成
- 智能采样统计计算

### load_optimizer.py 技术特性
- 跨平台硬件检测
- 二分搜索优化算法
- 自适应数据集采样
- 可视化结果生成
- JSON配置导出
- 命令行接口

---

## 🚀 推荐的完整工作流程 (基于实际代码能力)

```bash
# 步骤1: 硬件分析和负载优化
python load_optimizer.py --profile  # 查看硬件配置
python load_optimizer.py --ply-dir Ori_deformation/DeformedSampleJul_v1_Center --save-config optimal.json

# 步骤2: 验证相机配置
python sim2vfp.py --list-cameras

# 步骤3: 预览调整 (可选)
python sim2vfp.py --preview --preview-mode instance

# 步骤4: 使用优化负载进行渲染
python sim2vfp.py --parallel --load [OPTIMAL_LOAD]  # 使用优化器推荐的负载

# 步骤5: 交互式序列化配置
python sim2vfp.py --serialize
# 推荐选择:
# - 图像归一化: 选项2 (Dataset-specific)
# - 图像大小: 224×224
# - 力向量归一化: 启用，Z轴缩放因子10

# 步骤6: 验证序列化结果
python sim2vfp.py --visualize

# 步骤7: 集成DKNet训练 (在DKNet目录)
cd ../DKNet
python main.py --mode split --config configs/unified_config.yaml
python main.py --mode train --config configs/unified_config.yaml
```

### 优化建议
- 大型数据集(>40K文件): 使用load_optimizer.py进行采样优化
- 容器环境: 优先使用load_optimizer.py避免GUI限制
- 生产环境: 保存load_optimizer.py的JSON配置供重复使用
- 调试模式: 使用--visualize验证每个序列化配置

---

## License
MIT License © 2025