# dknet/utils/memory_monitor.py
import torch
import psutil
import threading
import time
import logging
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

class MemoryMonitor:
    """
    CPU & GPU Memory monitoring utility. Runs in background thread and logs
    memory usage at specified intervals.
    """
    def __init__(
        self,
        output_dir: str,
        interval: float = 1.0,
        plot: bool = True,
    ) -> None:
        """
        Initialize MemoryMonitor.

        Args:
            output_dir: Directory path for saving logs and plots
            interval: Monitoring interval in seconds
            plot: Whether to generate memory usage plots
        """
        if output_dir is None:
            raise ValueError(
                "MemoryMonitor requires a non-empty output_dir for logging "
                "and plots."
            )
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.interval = interval
        self.plot = plot

        self.timestamps = []
        self.gpu_allocated = []
        self.gpu_reserved = []
        self.gpu_max_allocated = 0
        self.gpu_max_reserved = 0
        self.cpu_used = []
        self.cpu_max_used = 0
        # Threading control
        self.running = False
        self.monitor_thread = None

    def _collect_memory_stats(self) -> dict:
        """Collect current memory usage statistics."""
        stats = {}

        # Collect GPU memory information
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            allocated = torch.cuda.memory_allocated() / (1024 ** 3)  # GB
            reserved = torch.cuda.memory_reserved() / (1024 ** 3)  # GB
            stats["gpu_allocated"] = allocated
            stats["gpu_reserved"] = reserved

            if allocated > self.gpu_max_allocated:
                # Update maximum allocated GPU memory
                self.gpu_max_allocated = allocated
            if reserved > self.gpu_max_reserved:
                # Update maximum reserved GPU memory
                self.gpu_max_reserved = reserved
        else:
            raise RuntimeError(
                "No CUDA device available for GPU memory monitoring"
            )

        # Collect CPU memory information
        process = psutil.Process()
        cpu_used = process.memory_info().rss / (1024 ** 3)  # GB
        stats["cpu_used"] = cpu_used

        if cpu_used > self.cpu_max_used:
            self.cpu_max_used = cpu_used

        return stats

    def _monitor_func(self) -> None:
        """Monitor thread main function."""
        while self.running:
            try:
                current_time = time.time()
                self.timestamps.append(current_time)

                stats = self._collect_memory_stats()
                self.gpu_allocated.append(stats["gpu_allocated"])
                self.gpu_reserved.append(stats["gpu_reserved"])
                self.cpu_used.append(stats["cpu_used"])

                time.sleep(self.interval)
            except Exception as e:
                # Keep monitoring alive even if a single sampling step fails.
                logging.error("Memory monitoring exception: %s", e)
                time.sleep(self.interval)

    def _generate_plot(self) -> None:
        """Generate memory usage plot."""
        # Convert timestamps to relative time (seconds)
        rel_times = np.array(self.timestamps) - self.timestamps[0]

        plt.figure(figsize=(12, 8))

        # Plot GPU memory usage
        plt.subplot(2, 1, 1)
        plt.plot(
            rel_times, self.gpu_allocated, label="Allocated", color="blue"
        )
        plt.plot(
            rel_times, self.gpu_reserved, label="Reserved", color="red", alpha=0.7
        )
        plt.axhline(
            y=self.gpu_max_allocated, linestyle="--", color="blue", alpha=0.5
        )
        plt.axhline(
            y=self.gpu_max_reserved, linestyle="--", color="red", alpha=0.5
        )
        plt.title("GPU Memory Usage (GB)")
        plt.legend()
        plt.grid(True, alpha=0.3)

        # Plot CPU memory usage
        plt.subplot(2, 1, 2)
        plt.plot(rel_times, self.cpu_used, label="Used", color="green")
        plt.axhline(
            y=self.cpu_max_used, linestyle="--", color="green", alpha=0.5
        )
        plt.title("CPU Memory Usage (GB)")
        plt.xlabel("Time (seconds)")
        plt.legend() 
        plt.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(self.output_dir / "memory_usage.png")

        with open(self.output_dir / "memory_stats.txt", "w") as f:
            f.write("Time(s),GPU_Allocated(GB),GPU_Reserved(GB),CPU_Used(GB)\n")
            for i in range(len(rel_times)):
                f.write(
                    f"{rel_times[i]:.2f},"
                    f"{self.gpu_allocated[i]:.4f},"
                    f"{self.gpu_reserved[i]:.4f},"
                    f"{self.cpu_used[i]:.4f}\n"
                )

    def __del__(self) -> None:
        """Ensure the background thread is stopped when the object is garbage-collected."""
        if self.running:
            self.running = False

    def start(self) -> None:
        """Start memory monitoring."""
        # Avoid starting multiple monitoring threads
        if self.running:
            logging.warning("Memory monitoring already running")
            return

        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_func)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

    def stop(self) -> None:
        """Stop memory monitoring.

        Must be called explicitly; relying on ``__del__`` alone does not
        guarantee a clean thread join before process exit.
        """
        self.running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            # Give some time for the thread to finish at most 2 seconds
            self.monitor_thread.join(timeout=2.0)
        # Only generate plot if enabled and there is data
        if self.plot and len(self.timestamps) > 1:
            self._generate_plot()
