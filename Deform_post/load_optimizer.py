"""
Intelligent Load Optimizer for sim2vfp.py
Automatically detects dataset size and provides optimal CPU load recommendations.
"""

import argparse
import hashlib
import json
import logging
import math
import multiprocessing as mp
import os
import platform
import subprocess
import time
import warnings
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

import psutil

# Attempt to import matplotlib for visualization
try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    warnings.warn("matplotlib not available - visualization features will be disabled", ImportWarning)

# Suppress matplotlib warnings if available
if MATPLOTLIB_AVAILABLE:
    warnings.filterwarnings('ignore', category=ImportWarning)


class HardwareInfo(NamedTuple):
    """Core hardware information for optimization."""
    cpu_model: str
    cpu_cores: int
    cpu_freq_ghz: float
    memory_gb: float
    memory_bandwidth_gbps: float
    memory_channels: int
    gpu_count: int
    gpu_models: List[str]
    gpu_memory_gb: List[float]
    max_test_workers: int  # Maximum workers to test (80% of cores)


class BenchmarkResult(NamedTuple):
    """Streamlined benchmark result."""
    load_percent: int
    workers: int
    throughput: float
    efficiency: float


class DatasetAnalyzer:
    """Intelligent dataset analysis and adaptive sampling.
    
    Provides adaptive sampling strategies based on dataset size to optimize
    benchmarking performance. Uses systematic sampling for better representation
    of the full dataset while maintaining reasonable testing times.
    
    Attributes:
        SAMPLING_STRATEGY: List of (threshold, ratio, description) tuples
                          defining sampling rates for different dataset sizes
    
    Example:
        >>> total, files = DatasetAnalyzer.scan_dataset('/path/to/ply/files')
        >>> sample_files, desc = DatasetAnalyzer.get_adaptive_sample(total, files)
        >>> print(f"Using {len(sample_files)} files: {desc}")
    """
    
    # Adaptive sampling thresholds
    SAMPLING_STRATEGY = [
        (1000, 1.0, "Small dataset - full testing"),
        (10000, 0.6, "Medium dataset - 60% sampling"),
        (50000, 0.3, "Large dataset - 30% sampling"),
        (100000, 0.18, "Huge dataset - 18% sampling"),
        (float('inf'), 0.1, "Massive dataset - 10% sampling")
    ]
    
    @staticmethod
    def scan_dataset(directory: str, pattern: str = "*.ply") -> Tuple[int, List[str]]:
        """Scan directory recursively for files matching the given pattern.
        
        Args:
            directory: Root directory path to scan
            pattern: File pattern to match (default: "*.ply")
            
        Returns:
            Tuple of (file_count, file_list) where:
            - file_count: Total number of matching files found
            - file_list: List of absolute file paths as strings
            
        Raises:
            FileNotFoundError: If the directory does not exist
            
        Example:
            >>> count, files = DatasetAnalyzer.scan_dataset('/data/ply_files')
            >>> print(f"Found {count} PLY files")
        """
        path = Path(directory)
        if not path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")
        
        # Use recursive search
        files = list(path.rglob(pattern))
        return len(files), [str(f) for f in files]
    
    @classmethod
    def get_adaptive_sample(cls, total_files: int, file_list: List[str]) -> Tuple[List[str], str]:
        """Select an adaptive sample from the file list based on dataset size.
        
        Uses systematic sampling to ensure representative coverage of the dataset
        while keeping sample sizes reasonable for optimization benchmarking.
        
        Args:
            total_files: Total number of files in the dataset
            file_list: Complete list of file paths
            
        Returns:
            Tuple of (sample_files, description) where:
            - sample_files: List of selected file paths for sampling
            - description: Human-readable description of the sampling strategy
            
        Example:
            >>> files = ['file1.ply', 'file2.ply', ...]
            >>> sample, desc = DatasetAnalyzer.get_adaptive_sample(1000, files)
            >>> print(desc)  # "Small dataset - full testing (1000/1000 files, 100.0%)"
        """
        for threshold, ratio, description in cls.SAMPLING_STRATEGY:
            if total_files <= threshold:
                sample_size = min(total_files, max(50, int(total_files * ratio)))
                
                # Systematic sampling for better representation
                if sample_size >= total_files:
                    return file_list, description
                
                step = total_files // sample_size
                sample_indices = list(range(0, total_files, step))[:sample_size]
                sample_files = [file_list[i] for i in sample_indices]
                
                description += f" ({sample_size}/{total_files} files, {ratio*100:.1f}%)"
                return sample_files, description
        
        # Fallback - should never reach here
        return file_list[:100], "Fallback sampling"


class CoreHardwareProfiler:
    """Streamlined hardware detection focused on core components.
    
    Provides cross-platform hardware profiling for CPU, memory, and GPU
    components essential for multiprocessing optimization. Uses caching
    to avoid repeated hardware detection calls.
    
    Features:
    - CPU model, cores, and frequency detection
    - Memory size, bandwidth, and channel information
    - GPU detection with memory capacity
    - Cross-platform compatibility (Linux, Windows)
    - LRU caching for performance
    
    Example:
        >>> hw = CoreHardwareProfiler.get_hardware_info()
        >>> print(f"CPU: {hw.cpu_model}, Memory: {hw.memory_gb:.0f}GB")
    """
    
    @staticmethod
    @lru_cache(maxsize=1)
    def get_hardware_info() -> HardwareInfo:
        """Detect and return comprehensive hardware information.
        
        Performs one-time hardware detection with LRU caching for subsequent calls.
        Uses platform-specific methods to gather accurate hardware details.
        
        Returns:
            HardwareInfo: Named tuple containing:
            - cpu_model: CPU model name
            - cpu_cores: Number of logical CPU cores
            - cpu_freq_ghz: Maximum CPU frequency in GHz
            - memory_gb: Total system memory in GB
            - memory_bandwidth_gbps: Memory bandwidth in GB/s
            - memory_channels: Number of memory channels
            - gpu_count: Number of detected GPUs
            - gpu_models: List of GPU model names
            - gpu_memory_gb: List of GPU memory sizes in GB
            - max_test_workers: Maximum worker count for testing (80% of cores)
            
        Example:
            >>> hw = CoreHardwareProfiler.get_hardware_info()
            >>> print(f"Max test workers: {hw.max_test_workers}")
        """
        # CPU info
        cpu_model = platform.processor()
        if not cpu_model:
            raise RuntimeError("Unable to detect CPU model")
        
        cpu_cores = psutil.cpu_count(logical=True)
        if not cpu_cores:
            raise RuntimeError("Unable to detect CPU core count")
        
        freq = psutil.cpu_freq()
        if not freq or not freq.max:
            raise RuntimeError("Unable to detect CPU frequency. Please ensure CPU frequency information is available.")
        cpu_freq = freq.max / 1000
        
        # Enhanced CPU detection
        if platform.system() == 'Linux':
            detailed_model = CoreHardwareProfiler._get_linux_cpu_model()
            if detailed_model:
                cpu_model = detailed_model
        elif platform.system() == 'Windows':
            detailed_model = CoreHardwareProfiler._get_windows_cpu_model()
            if detailed_model:
                cpu_model = detailed_model
        else:
            # Other systems (macOS, etc.) use basic detection only
            logging.debug(f"Enhanced CPU detection not available for {platform.system()}, using basic detection")
        
        # Memory info
        memory_gb = psutil.virtual_memory().total / (1024**3)
        if memory_gb <= 0:
            raise RuntimeError("Unable to detect system memory")
        
        try:
            memory_bandwidth_gbps, memory_channels = CoreHardwareProfiler._get_memory_bandwidth()
        except NotImplementedError:
            # Platform not supported for bandwidth detection
            memory_bandwidth_gbps, memory_channels = 0.0, 0
        
        # GPU info - handle cases where GPU detection might fail
        try:
            gpu_count, gpu_models, gpu_memory = CoreHardwareProfiler._get_gpu_info()
        except RuntimeError:
            # No GPU available or nvidia-smi not found
            gpu_count, gpu_models, gpu_memory = 0, [], []
        
        # Calculate maximum test range (80% of cores for upper bound)
        max_test_workers = int(cpu_cores * 0.8)
        if max_test_workers < 1:
            max_test_workers = 1
        
        return HardwareInfo(
            cpu_model=cpu_model,
            cpu_cores=cpu_cores,
            cpu_freq_ghz=cpu_freq,
            memory_gb=memory_gb,
            memory_bandwidth_gbps=memory_bandwidth_gbps,
            memory_channels=memory_channels,
            gpu_count=gpu_count,
            gpu_models=gpu_models,
            gpu_memory_gb=gpu_memory,
            max_test_workers=max_test_workers
        )
    
    @staticmethod
    def _get_linux_cpu_model() -> Optional[str]:
        """Extract CPU model name on Linux systems using lscpu.
        
        Returns:
            Optional[str]: CPU model name or None if detection fails
        """
        try:
            result = subprocess.run(['lscpu'], capture_output=True, text=True, timeout=5)
            for line in result.stdout.split('\n'):
                if 'Model name' in line:
                    return line.split(':')[1].strip()
        except:
            pass
        return None
    
    @staticmethod
    def _get_windows_cpu_model() -> Optional[str]:
        """Extract CPU model name on Windows systems using wmic.
        
        Returns:
            Optional[str]: CPU model name or None if detection fails
        """
        try:
            result = subprocess.run(
                ['wmic', 'cpu', 'get', 'Name', '/format:value'],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.split('\n'):
                if line.startswith('Name='):
                    return line.split('=', 1)[1].strip()
        except:
            pass
        return None
    
    @staticmethod
    def _get_memory_bandwidth() -> Tuple[float, int]:
        """Detect memory bandwidth and channel configuration.
        
        Uses platform-specific methods to determine memory performance
        characteristics.
        
        Returns:
            Tuple[float, int]: (bandwidth_gbps, channel_count)
            - bandwidth_gbps: Total memory bandwidth in GB/s
            - channel_count: Number of memory channels
        
        Raises:
            NotImplementedError: If running on unsupported platform
        """
        if platform.system() == 'Linux':
            return CoreHardwareProfiler._get_linux_memory_bandwidth()
        elif platform.system() == 'Windows':
            return CoreHardwareProfiler._get_windows_memory_bandwidth()
        
        raise NotImplementedError(f"Memory bandwidth detection not supported on {platform.system()}")
    
    @staticmethod
    def _get_linux_memory_bandwidth() -> Tuple[float, int]:
        """Extract memory bandwidth on Linux using dmidecode and lshw.
        
        Attempts multiple detection methods:
        1. dmidecode for detailed memory device info
        2. lshw for memory channel counting
        
        Returns:
            Tuple[float, int]: (bandwidth_gbps, channel_count)
            Returns (0.0, 0) if unable to detect actual values
        """
        bandwidth_gbps = 0.0
        channels = 0
        
        try:
            # Try dmidecode first (requires root access)
            result = subprocess.run(
                ['dmidecode', '-t', 'memory'],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                memory_devices = 0
                total_speed = 0
                
                for line in lines:
                    line = line.strip()
                    if 'Size:' in line and 'MB' in line and 'No Module Installed' not in line:
                        memory_devices += 1
                    elif 'Speed:' in line and 'MHz' in line:
                        try:
                            speed_mhz = int(line.split()[1])
                            total_speed += speed_mhz
                        except (IndexError, ValueError):
                            pass
                
                if memory_devices > 0 and total_speed > 0:
                    # Calculate bandwidth: Speed(MHz) * Width(64bit) * Channels / 8 / 1000
                    avg_speed_mhz = total_speed / memory_devices
                    bandwidth_gbps = (avg_speed_mhz * 64 * memory_devices) / 8 / 1000
                    channels = memory_devices
                    return bandwidth_gbps, channels
        
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        
        # Fallback: Try lshw
        try:
            result = subprocess.run(
                ['lshw', '-c', 'memory', '-short'],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'DIMM' in line and 'empty' not in line.lower():
                        channels += 1
        
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        
        # Return actual detected values only, no estimation
        return bandwidth_gbps, channels
    
    @staticmethod
    def _get_windows_memory_bandwidth() -> Tuple[float, int]:
        """Extract memory bandwidth on Windows using wmic commands.
        
        Queries memory chip information including speed and data width
        to calculate total bandwidth.
        
        Returns:
            Tuple[float, int]: (bandwidth_gbps, channel_count)
            Returns (0.0, 0) if unable to detect actual values
        """
        bandwidth_gbps = 0.0
        channels = 0
        
        try:
            # Get memory device info
            result = subprocess.run([
                'wmic', 'memorychip', 'get', 'Speed,DataWidth,DeviceLocator', '/format:csv'
            ], capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')[1:]  # Skip header
                total_speed = 0
                memory_devices = 0
                
                for line in lines:
                    if line.strip() and ',' in line:
                        parts = line.split(',')
                        if len(parts) >= 4:
                            try:
                                # Format: Node,DataWidth,DeviceLocator,Speed
                                speed_mhz = int(parts[3].strip())
                                # data_width = int(parts[1].strip()) if parts[1].strip() else 64  # Not used currently
                                
                                if speed_mhz > 0:
                                    total_speed += speed_mhz
                                    memory_devices += 1
                            except (ValueError, IndexError):
                                continue
                
                if memory_devices > 0 and total_speed > 0:
                    avg_speed_mhz = total_speed / memory_devices
                    # Calculate bandwidth: Speed(MHz) * Width(bits) * Channels / 8 / 1000
                    bandwidth_gbps = (avg_speed_mhz * 64 * memory_devices) / 8 / 1000
                    channels = memory_devices
                    return bandwidth_gbps, channels
        
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        
        # Return actual detected values only, no estimation
        return bandwidth_gbps, channels
    
    @staticmethod
    def _get_gpu_info() -> Tuple[int, List[str], List[float]]:
        """Detect GPU information using nvidia-smi.
        
        Attempts to detect NVIDIA GPUs with their model names and memory capacity.
        Searches common installation paths for nvidia-smi executable.
        
        Returns:
            Tuple[int, List[str], List[float]]: (gpu_count, gpu_models, gpu_memory_gb)
            - gpu_count: Number of detected GPUs
            - gpu_models: List of GPU model names
            - gpu_memory_gb: List of GPU memory sizes in GB
        
        Raises:
            RuntimeError: If nvidia-smi is not found or fails to execute
        """
        # Try nvidia-smi first
        nvidia_cmd = CoreHardwareProfiler._find_nvidia_smi()
        if not nvidia_cmd:
            raise RuntimeError(
                "nvidia-smi not found. Please ensure NVIDIA drivers are installed. "
                "If no GPU is present, this is expected."
            )
        
        try:
            result = subprocess.run([
                nvidia_cmd, '--query-gpu=name,memory.total', 
                '--format=csv,noheader'
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                models, memory = [], []
                for line in result.stdout.strip().split('\n'):
                    if line:
                        parts = line.split(',')
                        models.append(parts[0].strip())
                        mem_str = parts[1].strip().replace(' MiB', '')
                        memory.append(float(mem_str) / 1024)
                return len(models), models, memory
            else:
                raise RuntimeError(f"nvidia-smi failed with return code {result.returncode}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("nvidia-smi command timed out")
        except Exception as e:
            raise RuntimeError(f"Failed to execute nvidia-smi: {e}")
    
    @staticmethod
    def _find_nvidia_smi() -> Optional[str]:
        """Locate nvidia-smi executable across different installation paths.
        
        Searches common paths where nvidia-smi might be installed on
        Windows and Linux systems.
        
        Returns:
            Optional[str]: Path to nvidia-smi executable or None if not found
        """
        paths = [
            'nvidia-smi',
            'C:\\Program Files\\NVIDIA Corporation\\NVSMI\\nvidia-smi.exe',
            'C:\\Windows\\System32\\nvidia-smi.exe',
        ]
        
        for path in paths:
            try:
                result = subprocess.run([path, '-h'], capture_output=True, timeout=3)
                if result.returncode == 0:
                    return path
            except:
                continue
        return None


class OptimizationVisualizer:
    """Streamlined optimization results visualizer.
    
    Generates professional visualization charts showing CPU load optimization
    results including throughput and efficiency curves. Creates dual-axis
    plots with clear optimal point marking.
    
    Features:
    - Dual-axis plots (throughput + efficiency)
    - Optimal point highlighting with annotations
    - Professional styling with grid and legends
    - High-DPI PNG output (300 DPI)
    - Optional interactive display
    
    Example:
        >>> plot_path = OptimizationVisualizer.plot_results(results, 75)
        >>> print(f"Chart saved to: {plot_path}")
    """
    
    @staticmethod
    def plot_results(results: List[BenchmarkResult], optimal_load: int, 
                    save_path: str = None, show_plot: bool = False) -> Optional[str]:
        """Generate comprehensive visualization of optimization results.
        
        Creates a dual-panel chart showing throughput and efficiency curves
        across different CPU load percentages, with clear marking of the
        optimal configuration.
        
        Args:
            results: List of benchmark results to visualize
            optimal_load: Optimal CPU load percentage to highlight
            save_path: Custom file path for saving (auto-generated if None)
            show_plot: Whether to display the plot interactively
            
        Returns:
            Optional[str]: Path to saved plot file, or None if visualization failed
            
        Example:
            >>> results = [BenchmarkResult(50, 8, 45.2, 5.65), ...]
            >>> plot_file = OptimizationVisualizer.plot_results(results, 75)
            >>> print(f"Visualization saved: {plot_file}")
        """
        if not MATPLOTLIB_AVAILABLE:
            print("WARNING: matplotlib not available - skipping visualization")
            return None
            
        try:
            
            if not results:
                return None
                
            # Sort results by load percentage
            sorted_results = sorted(results, key=lambda r: r.load_percent)
            
            loads = [r.load_percent for r in sorted_results]
            throughputs = [r.throughput for r in sorted_results]
            efficiencies = [r.efficiency for r in sorted_results]
            
            # Create figure with subplots
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
            
            # Throughput plot
            ax1.plot(loads, throughputs, 'b-o', linewidth=2, markersize=8, 
                    markerfacecolor='lightblue', markeredgecolor='blue')
            ax1.set_xlabel('CPU Load (%)', fontsize=12, fontweight='bold')
            ax1.set_ylabel('Throughput (tasks/sec)', fontsize=12, fontweight='bold')
            ax1.set_title('Performance vs CPU Load', fontsize=14, fontweight='bold')
            ax1.grid(True, alpha=0.3)
            
            # Mark optimal point
            optimal_idx = next(i for i, r in enumerate(sorted_results) 
                             if r.load_percent == optimal_load)
            ax1.plot(optimal_load, throughputs[optimal_idx], 'ro', markersize=12, 
                    markerfacecolor='red', markeredgecolor='darkred', 
                    markeredgewidth=2, label=f'Optimal: {optimal_load}%')
            ax1.legend(fontsize=11)
            
            # Add performance annotation
            ax1.annotate(f'Peak: {throughputs[optimal_idx]:.0f} tasks/sec',
                        xy=(optimal_load, throughputs[optimal_idx]),
                        xytext=(optimal_load + 10, throughputs[optimal_idx] + max(throughputs) * 0.05),
                        arrowprops=dict(arrowstyle='->', color='red', lw=1.5),
                        fontsize=10, fontweight='bold', color='red')
            
            # Efficiency plot
            ax2.plot(loads, efficiencies, 'g-s', linewidth=2, markersize=8,
                    markerfacecolor='lightgreen', markeredgecolor='green')
            ax2.set_xlabel('CPU Load (%)', fontsize=12, fontweight='bold')
            ax2.set_ylabel('Efficiency Score', fontsize=12, fontweight='bold')
            ax2.set_title('Efficiency vs CPU Load', fontsize=14, fontweight='bold')
            ax2.grid(True, alpha=0.3)
            
            # Mark optimal efficiency
            optimal_efficiency = efficiencies[optimal_idx]
            ax2.plot(optimal_load, optimal_efficiency, 'ro', markersize=12,
                    markerfacecolor='red', markeredgecolor='darkred',
                    markeredgewidth=2, label=f'Optimal: {optimal_load}%')
            ax2.legend(fontsize=11)
            
            # Overall title
            fig.suptitle('CPU Load Optimization Results', fontsize=16, fontweight='bold', y=0.98)
            plt.tight_layout()
            plt.subplots_adjust(top=0.90)
            
            # Save plot
            if not save_path:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                save_path = f'optimization_results_{timestamp}.png'
            
            plt.savefig(save_path, dpi=300, bbox_inches='tight', 
                       facecolor='white', edgecolor='none')
            
            if show_plot:
                plt.show()
            else:
                plt.close()
                
            return save_path
            
        except Exception as e:
            print(f"WARNING: Visualization failed: {e}")
            return None


class FastLoadOptimizer:
    """Fast load optimization using binary search and early stopping.
    
    Implements an efficient optimization algorithm that uses binary search
    to find the optimal CPU load percentage with minimal benchmark runs.
    Reduces total optimization time from exhaustive testing while maintaining
    accuracy.
    
    Algorithm:
    1. Start with reasonable endpoints (20%, 80%)
    2. Use binary search to find gaps > precision threshold
    3. Dynamically calculate test count based on precision
    4. Select configuration with highest efficiency score

    Features:
    - Configurable precision binary search (default 5% threshold)
    - Adaptive test count: math.ceil(log2(60/precision)) + 2
    - Multiprocessing context management
    - Cross-platform compatibility
    
    Example:
        >>> optimizer = FastLoadOptimizer(simulate_task, sample_files)
        >>> optimal_load, results = optimizer.optimize()
        >>> print(f"Optimal load: {optimal_load}%")
    """
    
    def __init__(self, task_function: Callable, samples: List[str], precision: int = 5,
                 cpu_cores: int = None, cpu_freq_ghz: float = None):
        """Initialize the load optimizer.

        Args:
            task_function: Callable function that processes individual samples
            samples: List of sample file paths for benchmarking
            precision: Test precision threshold in percent (default: 5)
            cpu_cores: Number of CPU cores for strategy determination
            cpu_freq_ghz: CPU frequency in GHz for strategy determination
        """
        self.task_function = task_function
        self.samples = samples
        self.precision = precision
        self.results = []
        self.tested_loads = set()

        # Calculate maximum tests based on precision
        # For range [20%, 80%] = 60%, need log2(60/precision) + 2 safety margin
        self.max_additional_tests = max(4, math.ceil(math.log2(60 / precision)) + 2)

        # Determine optimization strategy based on hardware
        self.optimization_strategy = self._determine_optimization_strategy(cpu_cores, cpu_freq_ghz)

        # Setup minimal logging
        logging.basicConfig(level=logging.WARNING)

    def _determine_optimization_strategy(self, cpu_cores: int = None, cpu_freq_ghz: float = None) -> str:
        """Determine optimization strategy based on hardware performance.

        Uses Intel i7-14700KF (20 cores @ 3.4 GHz) as benchmark.
        Systems with performance >= benchmark use throughput priority,
        others use efficiency priority.

        Args:
            cpu_cores: Number of CPU cores
            cpu_freq_ghz: CPU base frequency in GHz

        Returns:
            str: Either 'throughput' or 'efficiency'
        """
        if cpu_cores is None or cpu_freq_ghz is None:
            # Default to efficiency if hardware info unavailable
            return 'efficiency'

        # Intel i7-14700KF benchmark: 20 cores @ 3.4 GHz = 68 performance units
        benchmark_score = 20 * 3.4
        current_score = cpu_cores * cpu_freq_ghz

        if current_score >= benchmark_score:
            return 'throughput'  # High-performance system: maximize total throughput
        else:
            return 'efficiency'  # Lower-performance system: maximize resource efficiency

    def optimize(self) -> Tuple[int, List[BenchmarkResult]]:
        """Find optimal CPU load using efficient binary search algorithm.

        Performs iterative binary search refinement to identify the CPU load
        percentage that maximizes either throughput or efficiency based on hardware.

        Returns:
            Tuple[int, List[BenchmarkResult]]: (optimal_load_percent, all_results)
            - optimal_load_percent: Best CPU load percentage (0-100)
            - all_results: List of all benchmark results for analysis

        Example:
            >>> optimal_load, results = optimizer.optimize()
            >>> print(f"Best configuration: {optimal_load}% CPU load")
        """
        # Start with endpoints
        candidates = [20, 80]  # Start with reasonable range

        # Test initial candidates
        for load in candidates:
            result = self._benchmark_load(load)
            self.results.append(result)
            self.tested_loads.add(load)

        # Binary search refinement
        for _ in range(self.max_additional_tests):  # Dynamic test count based on precision
            next_load = self._get_next_load()
            if next_load is None:
                break

            result = self._benchmark_load(next_load)
            self.results.append(result)
            self.tested_loads.add(next_load)

        # Find best result based on optimization strategy
        if self.optimization_strategy == 'throughput':
            best = max(self.results, key=lambda r: r.throughput)
        else:  # efficiency
            best = max(self.results, key=lambda r: r.efficiency)

        return best.load_percent, self.results
    
    def _get_next_load(self) -> Optional[int]:
        """Determine the next CPU load percentage to test.

        Finds the largest gap between tested loads and returns the midpoint
        for binary search refinement. Uses dynamic precision threshold.

        Returns:
            Optional[int]: Next load percentage to test, or None if done
        """
        sorted_results = sorted(self.results, key=lambda r: r.load_percent)

        # Find largest gap between tested loads
        max_gap = 0
        best_mid = None

        for i in range(len(sorted_results) - 1):
            current = sorted_results[i].load_percent
            next_load = sorted_results[i + 1].load_percent
            gap = next_load - current

            if gap > self.precision:  # Dynamic precision threshold
                mid = (current + next_load) // 2
                if mid not in self.tested_loads:
                    if gap > max_gap:
                        max_gap = gap
                        best_mid = mid

        return best_mid
    
    def _benchmark_load(self, load_percent: int) -> BenchmarkResult:
        """Benchmark a specific CPU load percentage configuration.
        
        Creates a multiprocessing pool with the specified number of workers
        and measures throughput and efficiency for the given load percentage.
        
        Args:
            load_percent: CPU load percentage (0-100)
            
        Returns:
            BenchmarkResult: Performance metrics for this configuration
            - load_percent: Tested CPU load percentage
            - workers: Number of worker processes used
            - throughput: Tasks processed per second
            - efficiency: Throughput per worker (tasks/sec/worker)
            
        Example:
            >>> result = optimizer._benchmark_load(75)
            >>> print(f"75% load: {result.throughput:.1f} tasks/sec")
        """
        workers = max(1, int(mp.cpu_count() * load_percent / 100))
        
        # Get multiprocessing context
        if platform.system() == 'Windows':
            ctx = mp.get_context("spawn")
        else:
            ctx = mp.get_context("spawn")  # Consistent across platforms
        
        # Quick benchmark
        start_time = time.time()
        
        with ctx.Pool(processes=workers) as pool:
            list(pool.map(self.task_function, self.samples))
        
        elapsed = time.time() - start_time
        throughput = len(self.samples) / elapsed if elapsed > 0 else 0
        
        # Simple efficiency metric
        efficiency = throughput / workers if workers > 0 else 0
        
        return BenchmarkResult(
            load_percent=load_percent,
            workers=workers,
            throughput=throughput,
            efficiency=efficiency
        )


class IntelligentLoadOptimizer:
    """Main intelligent load optimizer for sim2vfp.py.
    
    Comprehensive optimization system that analyzes PLY datasets and provides
    optimal CPU load recommendations for sim2vfp.py's parallel processing.
    Combines dataset analysis, hardware profiling, load optimization, and
    result visualization.
    
    Features:
    - Automatic dataset scanning and adaptive sampling
    - Cross-platform hardware profiling with memory bandwidth
    - Fast binary search optimization algorithm
    - Professional visualization with matplotlib
    - Direct integration commands for sim2vfp.py
    
    Workflow:
    1. Scan PLY directory and select representative samples
    2. Profile system hardware capabilities
    3. Benchmark multiple CPU load configurations
    4. Identify optimal load using efficiency metrics
    5. Generate visualization and recommendations
    
    Example:
        >>> optimizer = IntelligentLoadOptimizer('/path/to/ply/files')
        >>> results = optimizer.analyze_and_optimize()
        >>> print(results['recommendation'])
        "python sim2vfp.py --parallel --load 75"
    """
    
    def __init__(self, ply_directory: str, enable_plot: bool = True, plot_file: str = None, precision: int = 5):
        """Initialize the intelligent load optimizer.

        Args:
            ply_directory: Path to directory containing PLY files
            enable_plot: Whether to generate visualization charts
            plot_file: Custom filename for plot (auto-generated if None)
            precision: Test precision threshold in percent (default: 5)

        Raises:
            RuntimeError: If unable to detect critical hardware information
        """
        self.ply_directory = Path(ply_directory)
        try:
            self.hardware = CoreHardwareProfiler.get_hardware_info()
        except RuntimeError as e:
            print(f"ERROR: Failed to detect hardware information: {e}")
            raise
        self.enable_plot = enable_plot
        self.plot_file = plot_file
        self.precision = precision
        
    def analyze_and_optimize(self) -> Dict:
        """Execute complete dataset analysis and load optimization workflow.
        
        Performs the full optimization pipeline from dataset scanning through
        final recommendations. Displays progress information and generates
        visualization if enabled.
        
        Returns:
            Dict: Comprehensive optimization results containing:
            - dataset_files: Total number of PLY files found
            - sample_files: Number of files used for testing
            - optimal_load_percent: Recommended CPU load percentage
            - optimal_workers: Corresponding number of worker processes
            - hardware: Complete hardware profile information
            - recommendation: Direct command for sim2vfp.py execution
            
        Example:
            >>> optimizer = IntelligentLoadOptimizer('/data/ply_files')
            >>> results = optimizer.analyze_and_optimize()
            >>> print(f"Use {results['optimal_workers']} workers for optimal performance")
        """
        print(f"Scanning dataset: {self.ply_directory}")
        
        # Scan dataset
        total_files, file_list = DatasetAnalyzer.scan_dataset(str(self.ply_directory))
        sample_files, strategy_desc = DatasetAnalyzer.get_adaptive_sample(total_files, file_list)
        
        print(f"Dataset: {total_files:,} PLY files")
        print(f"Strategy: {strategy_desc}")
        
        # Display hardware info
        self._show_hardware_summary()
        
        # Optimize load
        print(f"\nOptimizing CPU load with {len(sample_files)} samples...")
        
        optimizer = FastLoadOptimizer(
            self._simulate_ply_task,
            sample_files,
            self.precision,
            self.hardware.cpu_cores,
            self.hardware.cpu_freq_ghz
        )
        optimal_load, results = optimizer.optimize()
        
        # Calculate optimal workers
        optimal_workers = max(1, int(mp.cpu_count() * optimal_load / 100))
        
        # Show results
        self._show_results(optimal_load, optimal_workers, results, optimizer.optimization_strategy)
        
        # Generate visualization
        plot_file = None
        if self.enable_plot:
            plot_file = OptimizationVisualizer.plot_results(results, optimal_load, self.plot_file)
            if plot_file:
                print(f"Visualization saved: {plot_file}")
        
        return {
            'dataset_files': total_files,
            'sample_files': len(sample_files),
            'optimal_load_percent': optimal_load,
            'optimal_workers': optimal_workers,
            'hardware': self.hardware._asdict(),
            'recommendation': f"python sim2vfp.py --parallel --load {optimal_load}"
        }
    
    def _show_hardware_summary(self):
        """Display concise hardware profile summary.
        
        Shows key hardware information including CPU, memory with bandwidth,
        GPU details (if available), and the test range that will be evaluated.
        """
        h = self.hardware
        print(f"\nHardware Profile:")
        print(f"   CPU: {h.cpu_model}")
        print(f"   Cores: {h.cpu_cores} @ {h.cpu_freq_ghz:.1f} GHz")
        if h.memory_bandwidth_gbps > 0:
            print(f"   Memory: {h.memory_gb:.0f} GB ({h.memory_bandwidth_gbps:.0f} GB/s, {h.memory_channels} channels)")
        else:
            print(f"   Memory: {h.memory_gb:.0f} GB")
        if h.gpu_count > 0:
            print(f"   GPU: {h.gpu_count}x {h.gpu_models[0] if h.gpu_models else 'Unknown'}")
        
        # Show test range instead of recommendation
        min_workers = max(1, int(h.cpu_cores * 0.2))
        max_workers = h.max_test_workers
        print(f"   Test Range: 20%-80% CPU load ({min_workers}-{max_workers} workers)")
    
    def _show_results(self, optimal_load: int, optimal_workers: int, results: List[BenchmarkResult], strategy: str):
        """Display comprehensive optimization results.

        Shows the optimal configuration, performance metrics, direct usage
        recommendation for sim2vfp.py, and summary of all tested configurations.

        Args:
            optimal_load: Best CPU load percentage found
            optimal_workers: Corresponding number of worker processes
            results: List of all benchmark results for comparison
            strategy: Optimization strategy used ('throughput' or 'efficiency')
        """
        # Find best results for both criteria
        best_throughput = max(results, key=lambda r: r.throughput)
        best_efficiency = max(results, key=lambda r: r.efficiency)

        # Determine which result was selected
        selected_result = next(r for r in results if r.load_percent == optimal_load)

        print(f"\nOptimization Results (Verified by Testing):")
        print(f"   Strategy: {strategy.upper()} optimization")
        print(f"   Selected: {optimal_load}% CPU load ({optimal_workers} workers)")
        print(f"   Performance: {selected_result.throughput:.1f} tasks/sec")
        print(f"   Efficiency: {selected_result.efficiency:.2f} tasks/sec/worker")

        # Show alternative optimum
        if strategy == 'throughput':
            if best_efficiency.load_percent != optimal_load:
                print(f"   Alternative (Efficiency): {best_efficiency.load_percent}% load -> {best_efficiency.efficiency:.2f} efficiency")
        else:
            if best_throughput.load_percent != optimal_load:
                print(f"   Alternative (Throughput): {best_throughput.load_percent}% load -> {best_throughput.throughput:.1f} tasks/sec")

        # Hardware performance context
        performance_score = self.hardware.cpu_cores * self.hardware.cpu_freq_ghz
        benchmark_score = 20 * 3.4  # i7-14700KF
        performance_ratio = performance_score / benchmark_score
        print(f"   Hardware Score: {performance_score:.1f} vs i7-14700KF baseline {benchmark_score:.1f} ({performance_ratio:.2f}x)")

        print(f"\nRecommendation for sim2vfp.py:")
        print(f"   python sim2vfp.py --parallel --load {optimal_load}")

        # Show all tested loads for reference
        print(f"\nTested Configurations:")
        for result in sorted(results, key=lambda r: r.load_percent):
            marker = "[OPTIMAL]" if result.load_percent == optimal_load else "         "
            print(f"   {marker} {result.load_percent:2d}% load -> {result.throughput:5.1f} tasks/sec (eff: {result.efficiency:.2f})")
    
    @staticmethod
    def _simulate_ply_task(ply_file: str) -> str:
        """Simulate realistic PLY file processing for benchmarking.
        
        Creates a CPU-intensive workload that mimics the computational
        characteristics of actual PLY file rendering and processing.
        Workload scales with file size to simulate real-world behavior.
        
        Args:
            ply_file: Path to PLY file to simulate processing
            
        Returns:
            str: Processing confirmation message
            
        Example:
            >>> result = IntelligentLoadOptimizer._simulate_ply_task('model.ply')
            >>> print(result)  # "Processed: model.ply"
        """
        
        # Simulate realistic PLY processing workload
        # - File I/O simulation
        file_size = os.path.getsize(ply_file) if os.path.exists(ply_file) else 100000
        
        # - CPU computation simulation (proportional to file size)
        iterations = max(100, file_size // 1000)
        for i in range(iterations):
            hashlib.md5(f"{ply_file}_{i}".encode()).hexdigest()
        
        return f"Processed: {Path(ply_file).name}"


def optimize_for_ply_directory(ply_dir: str, enable_plot: bool = True, plot_file: str = None, precision: int = 5) -> Dict:
    """Main entry point for PLY directory optimization.

    Convenience function that creates an IntelligentLoadOptimizer instance
    and runs the complete optimization workflow.

    Args:
        ply_dir: Directory path containing PLY files to analyze
        enable_plot: Whether to generate visualization charts (default: True)
        plot_file: Custom filename for visualization (auto-generated if None)
        precision: Test precision threshold in percent (default: 5)

    Returns:
        Dict: Complete optimization results with recommendations

    Example:
        >>> results = optimize_for_ply_directory('/data/models')
        >>> print(results['recommendation'])
        "python sim2vfp.py --parallel --load 75"
    """
    optimizer = IntelligentLoadOptimizer(ply_dir, enable_plot, plot_file, precision)
    return optimizer.analyze_and_optimize()


def get_hardware_profile() -> HardwareInfo:
    """Get detailed hardware profile without optimization.
    
    Convenience function for hardware profiling only, useful for
    system analysis or debugging.
    
    Returns:
        HardwareInfo: Complete hardware profile information
        
    Example:
        >>> hw = get_hardware_profile()
        >>> print(f"System has {hw.cpu_cores} cores and {hw.memory_gb:.0f}GB RAM")
    """
    return CoreHardwareProfiler.get_hardware_info()


if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(
        description="Intelligent Load Optimizer for sim2vfp.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --ply-dir Ori_deformation/DeformedSampleDec_v1
  %(prog)s --profile
  %(prog)s --ply-dir /path/to/ply/files --save-config optimal_load.json
  %(prog)s --ply-dir /path/to/ply/files --no-plot
  %(prog)s --ply-dir /path/to/ply/files --plot-file custom_results.png
  %(prog)s --ply-dir /path/to/ply/files --precision 3
        """
    )
    parser.add_argument("--ply-dir", type=str, help="Directory containing PLY files to analyze")
    parser.add_argument("--profile", action="store_true", help="Show hardware profile only")
    parser.add_argument("--save-config", type=str, help="Save optimization results to JSON file")
    parser.add_argument("--no-plot", action="store_true", help="Disable visualization generation")
    parser.add_argument("--plot-file", type=str, help="Custom filename for visualization (default: auto-generated)")
    parser.add_argument("--precision", type=int, default=5, help="Test precision threshold in percent (default: 5)")

    args = parser.parse_args()
    
    if args.profile:
        # Show hardware profile
        try:
            hardware = get_hardware_profile()
            print("Hardware Profile:")
            print(f"   CPU: {hardware.cpu_model}")
            print(f"   Cores: {hardware.cpu_cores} @ {hardware.cpu_freq_ghz:.1f} GHz") 
            print(f"   Memory: {hardware.memory_gb:.0f} GB", end="")
            if hardware.memory_bandwidth_gbps > 0:
                print(f" ({hardware.memory_bandwidth_gbps:.0f} GB/s, {hardware.memory_channels} channels)")
            else:
                print(" (bandwidth information not available)")
            if hardware.gpu_count > 0:
                for i, (model, mem) in enumerate(zip(hardware.gpu_models, hardware.gpu_memory_gb)):
                    print(f"   GPU {i}: {model} ({mem:.0f} GB)")
            print(f"   Max Parallel Capacity: {hardware.cpu_cores} workers")
            print(f"   Typical Test Range: 20%-80% CPU load")

            # Show test configuration
            max_tests = max(4, math.ceil(math.log2(60 / args.precision)) + 2)
            print(f"   Test Precision: {args.precision}% threshold")
            print(f"   Expected Tests: 2-{max_tests} (adaptive)")
            print(f"   Test Strategy: Binary search with early stopping")
        except RuntimeError as e:
            print(f"ERROR: Unable to detect hardware profile: {e}")
            exit(1)
        
    elif args.ply_dir:
        # Optimize for PLY directory
        try:
            enable_plot = not args.no_plot
            results = optimize_for_ply_directory(args.ply_dir, enable_plot, args.plot_file, args.precision)
            
            if args.save_config:
                with open(args.save_config, 'w') as f:
                    json.dump(results, f, indent=2, default=str)
                print(f"\nConfiguration saved to: {args.save_config}")
                
        except Exception as e:
            print(f"ERROR: {e}")
            exit(1)
            
    else:
        # Show usage
        parser.print_help()
        
        # Auto-detect common PLY directories
        common_dirs = [
            "Ori_deformation",
            "Ori_deformation/DeformedSampleDec_v1",
            "../Ori_deformation", 
        ]
        
        print("\nLooking for PLY directories...")
        for dir_path in common_dirs:
            if Path(dir_path).exists():
                try:
                    file_count, _ = DatasetAnalyzer.scan_dataset(dir_path)
                    if file_count > 0:
                        print(f"   Found: {dir_path} ({file_count:,} PLY files)")
                        print(f"   Usage: python {Path(__file__).name} --ply-dir {dir_path}")
                except:
                    pass