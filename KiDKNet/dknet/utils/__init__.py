# dknet/utils/__init__.py
"""
工具函数模块
=============================

提供损失函数、评估指标、可视化等核心工具功能的统一接口。
"""

# 损失函数 - 使用重构后的API
from .losses import (
    ForceLoss,                    # 主要损失函数工厂类
    MagnitudeAngleLoss,          # 幅度+角度组合损失（推荐）
    CosineDistance,          # 纯角度损失
    SineDistance,            # 正弦角度距离
    SquaredCosineDistance    # 余弦距离平方
)

# 评估指标 - 使用重构后的API
from .metrics import (
    compute_all_metrics,                    # 主要指标计算函数
    compute_loss_component_metrics,         # 损失组件指标
    denormalize_forces                      # 力向量反归一化
)

# 可视化功能 - 使用重构后的API
from .visualization import (
    # 训练可视化类
    TrainingVisualizer,
    # 评估可视化类
    EvaluateVisualizer,
    # 距离分布可视化
    plot_force_distance_histogram,
)

# Grad-CAM helpers
from .gradcam_visualization import (
    integrate_gradcam_to_evaluation,
    export_gradcam_basic_metrics_csv_for_loader,
)

# 内存监控功能
from .memory_monitor import MemoryMonitor

__all__ = [
    # 损失函数
    'ForceLoss', 'MagnitudeAngleLoss', 'CosineDistance',
    'SineDistance', 'SquaredCosineDistance',
    
    # 评估指标
    'compute_all_metrics', 'compute_loss_component_metrics',
    'denormalize_forces',
    
    # 可视化功能
    'TrainingVisualizer',
    'EvaluateVisualizer',
    'plot_force_distance_histogram',
    'integrate_gradcam_to_evaluation',
    'export_gradcam_basic_metrics_csv_for_loader',
    
    # 内存监控
    'MemoryMonitor',
]
