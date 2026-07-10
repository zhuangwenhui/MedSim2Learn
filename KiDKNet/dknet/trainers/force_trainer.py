# dknet/trainers/force_trainer.py
import os
import time
import logging
import torch
from torch.utils.data import DataLoader
from torch.optim.lr_scheduler import (
    ReduceLROnPlateau,
    CosineAnnealingLR,
    ExponentialLR,
    CyclicLR,
    OneCycleLR,
)
from torch.amp.autocast_mode import autocast
from torch.amp.grad_scaler import GradScaler
from tqdm import tqdm
from typing import Any, Optional

from ..utils.losses import ForceLoss
from ..utils.metrics import compute_all_metrics, compute_sequence_metrics
from ..utils.visualization import TrainingVisualizer, plot_force_distance_histogram
from ..utils.memory_monitor import MemoryMonitor
from ..utils.uda import coral_loss

def _fmt(value: Any, width: int, precision: int) -> str:
    """Format a numeric value for tabular display; returns 'N/A' on failure."""
    if value is None:
        return "N/A".rjust(width)
    try:
        return f"{float(value):{width}.{precision}f}"
    except (TypeError, ValueError):
        return "N/A".rjust(width)


def _render_table(rows: list[list[str]]) -> str:
    """Render a list of string rows as a fixed-width markdown-style table."""
    max_cols = max((len(row) for row in rows), default=0)
    normalized = [row + [""] * (max_cols - len(row)) for row in rows]
    col_widths = [
        max(len(normalized[r][c]) for r in range(len(normalized)))
        for c in range(max_cols)
    ]
    return "\n".join(
        "| " + " | ".join(f"{cell:<{col_widths[i]}}" for i, cell in enumerate(row)) + " |"
        for row in normalized
    )


class ForceTrainer:

    def __init__(
        self,
        model,
        config: dict[str, Any],
        train_loader: DataLoader,
        val_loader: DataLoader,
        experiment_name: str,
        experiment_dir: str,
    ) -> None:
        # CUDA check - enforce GPU usage
        if not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA device is required for ForceTrainer; no GPU is available."
            )
        self.device = torch.device("cuda")

        # Initialize model
        if model is None:
            raise ValueError("Model instance must be provided to ForceTrainer.")
        self.model = model

        # Initialize config
        if config is None:
            raise ValueError("Configuration dictionary is required for ForceTrainer.")
        if not isinstance(config, dict):
            raise TypeError("Configuration must be provided as a dictionary.")
        self.config: dict[str, Any] = config

        # Initialize dataloaders
        if train_loader is None or val_loader is None:
            raise ValueError("Training and validation data loaders must be provided to ForceTrainer.")
        self.train_loader: DataLoader = train_loader
        self.val_loader: DataLoader = val_loader
        # Track B UDA (default OFF). scripts/train.py sets these after construction
        # when training.adaptation.enabled; left as no-ops otherwise so the default
        # training path is byte-identical (coral_weight 0.0 -> encoder-CORAL skipped).
        self.target_train_loader: Optional[DataLoader] = None
        self.coral_weight: float = 0.0
        # Get force vector normalization information (Already synchronized with dataloader)
        self.normalize_forces = self.config["data"].get("normalize_forces", False)
        self.force_normalization = self.config["data"].get("force_normalization", None)

        # Set experiment name and directory
        if experiment_name is None:
            raise ValueError("Experiment name must be provided to ForceTrainer.")
        self.experiment_name: str = experiment_name

        if not experiment_dir:
            raise ValueError("Experiment directory must be provided to ForceTrainer.")
        self.exp_output_dir = experiment_dir
        self.checkpoint_dir = os.path.join(self.exp_output_dir, "checkpoints")
        os.makedirs(self.checkpoint_dir, exist_ok=True)

        # Set up logger
        self.logger = self._setup_logger()
        if self.normalize_forces:
            self.logger.info(f"Force vector normalization enabled: {self.force_normalization}")

        # Move model to device
        self.model = self.model.to(self.device)
        # Optional weight initialization for transfer (cond4): load a checkpoint's
        # weights only (strict=False) -- NOT a resume; optimizer/scheduler/epoch
        # start fresh. Done before _setup_training_params so freezing applies to
        # the initialized weights.
        init_ckpt = (
            config.get("training", {}).get("transfer", {}) or {}
        ).get("init_from_checkpoint")
        if init_ckpt:
            self._load_init_checkpoint(init_ckpt)
        # Set up training parameters
        self._setup_training_params()

        # Initialize tracking variables
        self.epoch = 0
        self.best_val_metric = float('inf')    # Lower is better for validation loss
        self.best_epoch = 0
        self.train_metrics_history = []
        self.val_metrics_history = []

        # Initialize training visualizer
        self.visualizer = TrainingVisualizer(
            save_dir=os.path.join(self.exp_output_dir, "visualizations"),
            experiment_name=self.experiment_name
        )
        self._distance_hist_limits = None

        # Initialize memory monitor
        memory_config = config["monitoring"]
        if memory_config["enable_memory_monitoring"]:
            self.memory_monitor = MemoryMonitor(
                output_dir=os.path.join(self.exp_output_dir, "memory_monitoring"),
                interval=memory_config.get("memory_monitor_interval", 1.0),
                plot=True
            )
        else:
            self.memory_monitor = None

        # Initialize loss component history
        self.loss_component_history = {
            'train_magnitude_loss': [],
            'train_angle_loss': [],
            'val_magnitude_loss': [],
            'val_angle_loss': []
        }

        self.logger.info(f"Trainer initialized, device: {self.device}")
        self.logger.info(f"Model: {type(model).__name__}")
        if self.train_loader is not None:
            self.logger.info(
                f"Training loader batches: {len(self.train_loader)}, "
                f"batch size: {self.train_loader.batch_size}"
            )
        if self.val_loader is not None:
            self.logger.info(
                f"Validation loader batches: {len(self.val_loader)}, "
                f"batch size: {self.val_loader.batch_size}"
            )

        # Optional Weights & Biases tracking (opt-in via config["wandb"]).
        self._init_wandb()
    
    # Currently disable GPU memory logging methods for cleaner output
    # The methods can be re-enabled if detailed memory tracking is needed later
    def _log_gpu_memory(self, location: str = "") -> None:
        """Monitor and log GPU memory usage."""
        gb = float(1024 ** 3)
        allocated = torch.cuda.memory_allocated() / gb
        max_allocated = torch.cuda.max_memory_allocated() / gb
        reserved = torch.cuda.memory_reserved() / gb

        self.logger.info(
            f"GPU memory status {location} - "
            f"Current: {allocated:.2f} GB; "
            f"Peak: {max_allocated:.2f} GB; "
            f"Reserved: {reserved:.2f} GB"
        )
    
    def _cleanup_memory(self, synchronize: bool = False) -> None:
        """Cleanup GPU memory by optionally synchronizing and emptying cache."""
        if synchronize:
            torch.cuda.synchronize()
        torch.cuda.empty_cache()
        self.logger.debug("GPU cache memory cleared")
    
    def _prefetch_batch(self, data_iter, stream=None):
        """Prefetch a batch of data and move it to the device asynchronously."""
        try:
            batch = next(data_iter)
        except StopIteration:
            return None

        images = batch.get('image')
        forces = batch.get('force')
        # Keep non-tensor metadata (e.g., id) so callers still get full batch info.
        remaining = {k: v for k, v in batch.items() if k not in ('image', 'force')}

        if images is None or forces is None:
            raise KeyError('Expected keys "image" and "force" in batch data')

        if stream is not None:
            # Move tensors on a dedicated stream when provided to overlap copy and compute.
            with torch.cuda.stream(stream):
                images = images.to(self.device, non_blocking=True)
                forces = forces.to(self.device, non_blocking=True)
        else:
            # Fall back to the default stream when no prefetch stream is passed.
            images = images.to(self.device, non_blocking=True)
            forces = forces.to(self.device, non_blocking=True)

        # Reattach moved tensors so the returned batch stays complete.
        remaining['image'] = images
        remaining['force'] = forces
        # Hand back tensors (now on GPU) plus untouched metadata.
        return remaining

    def _setup_logger(self) -> logging.Logger:
        """Set up a specific logger for the experiment."""
        # Create a logger with the experiment name
        logger = logging.getLogger(f"ForceTrainer_")
        # Set the minimum logging level to INFO
        logger.setLevel(logging.INFO)

        # Only create a file handler
        # Console output is handled by global logging.basicConfig
        # Create logs directory for the experiment
        logs_dir = os.path.join(self.exp_output_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        # Record logs to a file to capture detailed training information
        # This helps in debugging and analyzing training progress over time
        # -> DKNET/outputs/experiments/EXP_NAME/logs/training.log
        log_file = os.path.join(logs_dir, "training.log")
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        # Set formatter for the file handler to include timestamp, logger name, level, and message
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        # Add the file handler to the logger
        logger.addHandler(file_handler)

        return logger
    
    def _setup_training_params(self) -> None:
        """Set up training parameters from the configuration."""
        train_cfg = self.config["training"]
        # Basic training parameters
        self.batch_size = train_cfg.get("batch_size", 32)
        self.epochs = train_cfg.get("epochs", 100)
        self.early_stopping_patience = train_cfg.get("early_stopping_patience", 10)
        self.prefetch_to_gpu = train_cfg.get("prefetch_to_gpu", True)
        # GPU memory optimization: tune per-step footprint and cache clearing cadence
        self.grad_accum_steps = train_cfg.get("gradient_accumulation_steps", 1)
        # 0 disables periodic empty_cache during training steps.
        self.empty_cache_freq = int(train_cfg.get("empty_cache_freq", 2))
        if self.grad_accum_steps > 1:
            self.logger.info(f"Gradient accumulation enabled: {self.grad_accum_steps} steps")

        # Mixed precision setup
        # H100/A100 use bfloat16, others use float16 by default
        mp_cfg = train_cfg.get("mixed_precision", {})
        self.use_amp = bool(mp_cfg.get("enabled", True))
        dtype_setting = mp_cfg.get("dtype", "auto")
        if dtype_setting == "auto":
            sm_major, _ = torch.cuda.get_device_capability(self.device)
            self.amp_dtype = torch.bfloat16 if sm_major >= 8 else torch.float16
        elif dtype_setting == "bfloat16":
            self.amp_dtype = torch.bfloat16
        elif dtype_setting == "float16":
            self.amp_dtype = torch.float16
        else:
            raise ValueError(f"Unsupported mixed_precision dtype: {dtype_setting}")
        # Initialize GradScaler if using AMP (Necessary for automatic mixed precision training)
        self.grad_scaler: Optional[GradScaler] = None
        if self.use_amp:
            self.grad_scaler = GradScaler(enabled=True)

        # Optimizer setup
        optim_cfg = train_cfg.get("optimizer", {})
        if not optim_cfg:
            raise ValueError(
                "Optimizer configuration is missing. Please check training.optimizer settings."
            )
        base_optimizer_type = optim_cfg.get("type", "adam")
        # If user specifies "sgd", map to "sgdm" for momentum SGD
        if isinstance(base_optimizer_type, str) and base_optimizer_type.lower() == "sgd":
            base_optimizer_type = "sgdm"
        self.optimizer_type = base_optimizer_type
        self.learning_rate = optim_cfg.get("learning_rate", 1e-3)
        self.weight_decay = optim_cfg.get("weight_decay", 0)
        # SGD-specific parameters
        if self.optimizer_type.lower() == "sgdm":
            self.momentum = optim_cfg.get("momentum", 0.9)
            self.dampening = optim_cfg.get("dampening", 0.0)
            self.nesterov = optim_cfg.get("nesterov", False)

        # Transfer-learning (cond4) setup: LP-FT staged unfreeze + discriminative
        # LR. The optimizer is built ONCE over discriminative param groups;
        # backbone params frozen during the linear-probe phase simply receive no
        # gradient until unfrozen, so no optimizer rebuild is needed.
        self.transfer_cfg = train_cfg.get("transfer", {}) or {}
        self.transfer_enabled = bool(self.transfer_cfg.get("enabled", False))
        self.lp_epochs = int(self.transfer_cfg.get("linear_probe_epochs", 0))
        self.backbone_lr_scale = float(self.transfer_cfg.get("backbone_lr_scale", 1.0))
        # None/empty -> unfreeze the whole backbone after the probe; a list of
        # ConvNeXt feature-block indices -> surgical fine-tuning of those blocks.
        self.finetune_stages = self.transfer_cfg.get("finetune_stages")
        self._backbone_unfrozen = not (self.transfer_enabled and self.lp_epochs > 0)
        if self.transfer_enabled and self.lp_epochs > 0:
            self._set_backbone_requires_grad(False)
            self.logger.info(
                "[transfer] linear-probe phase: backbone frozen for %d epoch(s); "
                "backbone_lr_scale=%.3g, finetune_stages=%s",
                self.lp_epochs, self.backbone_lr_scale,
                self.finetune_stages or "all",
            )

        # Sequence (clip-to-per-frame) vs single-image model. The sequence model
        # returns a LIST of (B, T, 3) stage outputs and is scored per-frame.
        self.is_sequence_model = (
            self.config["model"].get("name") == "sequence_forcenet"
        )
        if self.is_sequence_model:
            self.logger.info(
                "Sequence model detected: per-frame metrics + deep-supervision "
                "loss over (B, T, 3) stage outputs."
            )

        # Loss function setup (built BEFORE the optimizer so any learnable loss
        # parameters -- e.g. uncertainty-weighting log-variances -- can be folded
        # into the optimizer below). Moved to device so loss params/buffers live
        # on the same device as the model.
        loss_cfg = train_cfg.get("loss", {})
        self.loss_type = loss_cfg.get("type", "COMBINED")
        loss_kwargs = {k: v for k, v in loss_cfg.items() if k != "type"}
        self.loss_fn = ForceLoss.get_loss(self.loss_type, **loss_kwargs).to(self.device)
        # Check if the loss function supports component monitoring
        self.supports_component_monitoring = hasattr(self.loss_fn, 'get_component_losses')

        # Build the optimizer now that the loss exists; _create_optimizer folds
        # in self.loss_fn.parameters() when the loss carries learnable params.
        self.optimizer = self._create_optimizer()
        if self.supports_component_monitoring:
            self.logger.info(f"Loss function {self.loss_type} supports component monitoring")
        else:
            self.logger.info(f"Loss function {self.loss_type} does not support component monitoring")

        # Learning rate scheduler setup
        scheduler_cfg = train_cfg.get("scheduler", {})
        if not scheduler_cfg:
            raise ValueError(
                "Scheduler configuration is missing. Please check training.scheduler settings."
            )
        # Instantiate scheduler
        self.scheduler = self._create_scheduler(scheduler_cfg)

        log_cfg = self.config.get("logging", {}) or {}
        self.keep_last = max(0, int(log_cfg.get("keep_last", 5)))
        self.keep_best = bool(log_cfg.get("keep_best", True))

    def _format_epoch_summary(
            self, stage: str, epoch_loss: float, metrics: dict[str, Any]
        ) -> str:
        epoch_label = f"{self.epoch + 1}/{self.epochs}"
        mag_loss = metrics.get("loss_magnitude_component") if self.supports_component_monitoring else None
        ang_loss = metrics.get("loss_angle_component") if self.supports_component_monitoring else None

        mag_acc = metrics.get("magnitude_accuracy_10pct")
        ang_acc = metrics.get("angle_accuracy_5deg")
        denorm_mag_acc = metrics.get("denorm_magnitude_accuracy_10pct") if self.normalize_forces else None
        denorm_ang_acc = metrics.get("denorm_angle_accuracy_5deg") if self.normalize_forces else None

        mag_mre = metrics.get("magnitude_mean_relative_error")
        mag_mae = metrics.get("magnitude_mean_absolute_error")
        ang_mean_err = metrics.get("mean_angle_error")

        x_mae = metrics.get("x_mae")
        y_mae = metrics.get("y_mae")
        z_mae = metrics.get("z_mae")

        line1 = f"{stage} Epoch: {epoch_label}"

        rows = [
            [
                f"Loss: {_fmt(epoch_loss, 10, 6)}",
                f"Mag Loss: {_fmt(mag_loss, 8, 4)}",
                f"Ang Loss: {_fmt(ang_loss, 8, 4)}",
                "",
            ],
            [
                f"Mag ACC@10%: {_fmt(mag_acc, 7, 4)}",
                f"Ang ACC@5°: {_fmt(ang_acc, 7, 4)}",
                f"Denorm Mag ACC@10%: {_fmt(denorm_mag_acc, 7, 4)}" if self.normalize_forces else "",
                f"Denorm Ang ACC@5°: {_fmt(denorm_ang_acc, 7, 4)}" if self.normalize_forces else "",
            ],
            [
                f"Mag MRE: {_fmt(mag_mre, 8, 4)}",
                f"Mag MAE: {_fmt(mag_mae, 8, 4)}",
                f"Ang Mean Err(°): {_fmt(ang_mean_err, 9, 4)}",
                "",
            ],
            [
                f"X MAE: {_fmt(x_mae, 8, 4)}",
                f"Y MAE: {_fmt(y_mae, 8, 4)}",
                f"Z MAE: {_fmt(z_mae, 8, 4)}",
                "",
            ],
        ]

        return "\n".join([line1, _render_table(rows)])
    
    def _create_optimizer(self):
        """Create the configured optimizer.

        For transfer runs the backbone is placed in its own param group at a
        scaled (usually smaller) learning rate (discriminative LR); otherwise all
        parameters share one group.
        """
        # Learnable loss parameters (e.g. uncertainty-weighting log-variances);
        # empty for the default param-less losses, so this stays byte-identical.
        _loss_mod = getattr(self, "loss_fn", None)
        loss_params = list(_loss_mod.parameters()) if _loss_mod is not None else []
        if self.transfer_enabled:
            params = list(self._transfer_param_groups())
            if loss_params:
                params = params + [
                    {"params": loss_params, "lr": self.learning_rate,
                     "weight_decay": 0.0}
                ]
        elif loss_params:
            params = [
                {"params": list(self.model.parameters())},
                {"params": loss_params, "weight_decay": 0.0},
            ]
        else:
            params = self.model.parameters()
        if self.optimizer_type.lower() == "adam":
            return torch.optim.Adam(
                params,
                lr=self.learning_rate,
                weight_decay=self.weight_decay
            )

        elif self.optimizer_type.lower() == "sgdm":
            return torch.optim.SGD(
                params,
                lr=self.learning_rate,
                momentum=self.momentum,
                dampening=self.dampening,
                weight_decay=self.weight_decay,
                nesterov=self.nesterov
            )

        elif self.optimizer_type.lower() == "adamw":
            return torch.optim.AdamW(
                params,
                lr=self.learning_rate,
                weight_decay=self.weight_decay
            )

        else:
            raise ValueError(f"Unsupported optimizer type: {self.optimizer_type}")

    # ------------------------------------------------------------------ #
    # Transfer learning (cond4): LP-FT + discriminative LR + weight init
    # ------------------------------------------------------------------ #
    def _backbone_module(self):
        """Return the model's frame encoder, or None if it has no backbone."""
        return getattr(self.model, "backbone", None)

    def _set_backbone_requires_grad(self, requires_grad: bool) -> None:
        """Toggle requires_grad over all backbone parameters."""
        backbone = self._backbone_module()
        if backbone is None:
            return
        for param in backbone.parameters():
            param.requires_grad = requires_grad

    def _transfer_param_groups(self):
        """Discriminative-LR param groups: backbone at a scaled LR, rest at base."""
        backbone = self._backbone_module()
        backbone_ids = (
            {id(p) for p in backbone.parameters()} if backbone is not None else set()
        )
        backbone_params = [
            p for p in self.model.parameters() if id(p) in backbone_ids
        ]
        other_params = [
            p for p in self.model.parameters() if id(p) not in backbone_ids
        ]
        groups = [{"params": other_params, "lr": self.learning_rate}]
        if backbone_params:
            groups.append({
                "params": backbone_params,
                "lr": self.learning_rate * self.backbone_lr_scale,
            })
        return groups

    def _unfreeze_backbone(self) -> None:
        """Unfreeze the whole backbone, or only the configured ConvNeXt blocks."""
        backbone = self._backbone_module()
        if backbone is None:
            return
        stages = self.finetune_stages
        features = getattr(getattr(backbone, "model", None), "features", None)
        if not stages or features is None:
            self._set_backbone_requires_grad(True)
            return
        # Surgical fine-tuning: unfreeze only the selected feature blocks.
        for idx in stages:
            if 0 <= int(idx) < len(features):
                for param in features[int(idx)].parameters():
                    param.requires_grad = True

    def _apply_transfer_phase(self, epoch: int) -> None:
        """At the end of the linear-probe phase, unfreeze the backbone once."""
        if not self.transfer_enabled or self._backbone_unfrozen:
            return
        if epoch >= self.lp_epochs:
            self._unfreeze_backbone()
            self._backbone_unfrozen = True
            trainable = sum(
                p.numel() for p in self.model.parameters() if p.requires_grad
            )
            self.logger.info(
                "[transfer] epoch %d: unfroze backbone (stages=%s); "
                "trainable params now %s",
                epoch + 1, self.finetune_stages or "all", f"{trainable:,}",
            )

    def _load_init_checkpoint(self, ckpt_path: str) -> None:
        """Initialize model weights from a checkpoint (NOT a resume).

        Loads only the model_state_dict with strict=False so a synt-pretrained
        single-image checkpoint can seed a real fine-tune (cond4), or a
        single-image backbone can seed a sequence model. Optimizer, scheduler,
        epoch counter, and history all start fresh.
        """
        if not os.path.exists(ckpt_path):
            raise FileNotFoundError(
                f"transfer.init_from_checkpoint not found: {ckpt_path}"
            )
        ckpt = torch.load(ckpt_path, map_location=self.device, weights_only=False)
        state = ckpt.get("model_state_dict", ckpt) if isinstance(ckpt, dict) else ckpt
        result = self.model.load_state_dict(state, strict=False)
        self.logger.info(
            "[transfer] initialized weights from %s (missing=%d, unexpected=%d)",
            ckpt_path, len(result.missing_keys), len(result.unexpected_keys),
        )

    def _create_scheduler(self, scheduler_cfg: dict[str, Any]):
        """Create the configured learning rate scheduler."""
        self.scheduler_type = scheduler_cfg.get("type", "plateau")

        if self.scheduler_type.lower() == "plateau":
            self.scheduler_factor = scheduler_cfg.get("factor", 0.5)
            self.scheduler_patience = scheduler_cfg.get("patience", 5)
            min_lr = scheduler_cfg.get("min_lr")
            threshold = scheduler_cfg.get("threshold") 

            kwargs = {
                "mode": "min",
                "factor": self.scheduler_factor,
                "patience": self.scheduler_patience,
            }

            if min_lr is not None:
                # Include min_lr in kwargs only if configured
                kwargs["min_lr"] = min_lr
            if threshold is not None:
                # Include threshold in kwargs only if configured
                kwargs["threshold"] = threshold

            return ReduceLROnPlateau(self.optimizer, **kwargs)

        if self.scheduler_type.lower() == "cosine":
            t_max = scheduler_cfg.get("t_max", self.epochs)
            eta_min = scheduler_cfg.get("eta_min", 1e-6)

            return CosineAnnealingLR(
                self.optimizer,
                T_max=t_max,
                eta_min=eta_min,
            )

        if self.scheduler_type.lower() == "exponential":
            gamma = scheduler_cfg.get("gamma", 0.99)

            return ExponentialLR(self.optimizer, gamma=gamma)

        if self.scheduler_type.lower() == "cyclic":
            base_lr = scheduler_cfg.get("base_lr")
            max_lr = scheduler_cfg.get("max_lr")
            if base_lr is None or max_lr is None:
                raise ValueError("CyclicLR requires 'base_lr' and 'max_lr' in scheduler configuration.")

            step_size_up = scheduler_cfg.get("step_size_up")
            if step_size_up is None:
                raise ValueError("CyclicLR requires 'step_size_up'; please check scheduler configuration.")
            step_size_down = scheduler_cfg.get("step_size_down", step_size_up)

            # If mode not specified, default to 'triangular2'
            mode = scheduler_cfg.get("mode", "triangular2")
            gamma = scheduler_cfg.get("gamma", 1.0)

            cycle_momentum = scheduler_cfg.get("cycle_momentum")
            if cycle_momentum is None:
                # Only cycle momentum for SGD-based optimizers, close otherwise
                cycle_momentum = self.optimizer_type.lower() in {"sgd", "sgdm"}
            base_momentum = scheduler_cfg.get("base_momentum", 0.85)
            max_momentum = scheduler_cfg.get("max_momentum", 0.95)

            return CyclicLR(
                self.optimizer,
                base_lr=base_lr,
                max_lr=max_lr,
                step_size_up=step_size_up,
                step_size_down=step_size_down,
                mode=mode,
                gamma=gamma,
                cycle_momentum=cycle_momentum,
                base_momentum=base_momentum,
                max_momentum=max_momentum,
            )

        if self.scheduler_type.lower() == "onecycle":
            epochs = scheduler_cfg.get("epochs", self.epochs)
            max_lr = scheduler_cfg.get("max_lr")
            if max_lr is None:
                raise ValueError("OneCycleLR requires 'max_lr' in scheduler configuration.")

            total_steps = scheduler_cfg.get("total_steps")
            steps_per_epoch = scheduler_cfg.get("steps_per_epoch")
            if total_steps is None:
                if steps_per_epoch is None and self.train_loader is not None:
                    steps_per_epoch = len(self.train_loader)
                if steps_per_epoch is None or steps_per_epoch == 0:
                    raise ValueError("OneCycleLR requires 'total_steps' or an initialised training loader.")

            cycle_momentum = scheduler_cfg.get("cycle_momentum")
            if cycle_momentum is None:
                # Only cycle momentum for SGD-based optimizers, close otherwise
                cycle_momentum = self.optimizer_type.lower() in {"sgd", "sgdm"}

            common_kwargs = {
                "pct_start": scheduler_cfg.get("pct_start", 0.3),
                "anneal_strategy": scheduler_cfg.get("anneal_strategy", "cos"),
                "cycle_momentum": cycle_momentum,
                "base_momentum": scheduler_cfg.get("base_momentum", 0.85),
                "max_momentum": scheduler_cfg.get("max_momentum", 0.95),
                "div_factor": scheduler_cfg.get("div_factor", 25.0),
                "final_div_factor": scheduler_cfg.get("final_div_factor", 1e4),
            }
            if total_steps is not None:
                return OneCycleLR(
                    self.optimizer,
                    max_lr=max_lr,
                    total_steps=total_steps,
                    **common_kwargs,
                )
            # Use epochs and steps_per_epoch
            return OneCycleLR(
                self.optimizer,
                max_lr=max_lr,
                steps_per_epoch=steps_per_epoch,
                epochs=epochs,
                **common_kwargs,
            )
        
        raise ValueError(f"Unsupported scheduler type: {self.scheduler_type}")

    def _final_pred(self, outputs):
        """Final-stage prediction for metric accumulation.

        The sequence model returns a list of per-stage (B, T, 3) tensors (deep
        supervision); the last element is the refined prediction. The single
        image model returns a (B, 3) tensor directly.
        """
        if self.is_sequence_model and isinstance(outputs, (list, tuple)):
            return outputs[-1]
        return outputs

    def _compute_metrics(self, predictions, targets):
        """Dispatch to the per-frame sequence metrics or the single-image ones."""
        metric_fn = (
            compute_sequence_metrics if self.is_sequence_model else compute_all_metrics
        )
        return metric_fn(
            predictions,
            targets,
            force_normalization=self.force_normalization if self.normalize_forces else None,
            include_denormalized=self.normalize_forces,
            loss_fn=self.loss_fn if self.supports_component_monitoring else None,
        )

    def _forward_loss(self, images, targets, tgt_images):
        """Task loss, plus the CORAL domain-alignment term when UDA is active.

        When active, one encoder forward yields both the source prediction and
        feature; CORAL(source_feat, target_feat) is computed in float32 (covariance
        stability under AMP) and added as coral_weight * CORAL. When inactive this
        is the exact original forward+loss, so the default path is byte-identical.
        """
        if getattr(self, "_coral_active", False) and tgt_images is not None:
            outputs, feat_src = self.model(images, return_features=True)
            loss = self.loss_fn(outputs, targets)
            feat_tgt = self.model.backbone(tgt_images)
            loss = loss + self.coral_weight * coral_loss(feat_src.float(), feat_tgt.float())
        else:
            outputs = self.model(images)
            loss = self.loss_fn(outputs, targets)
        return outputs, loss

    def train_epoch(self):
        """Train the model for one epoch"""
        # Set model to training mode
        self.model.train()
        # During the linear-probe phase keep the frozen backbone in eval mode so
        # its features are deterministic (no stochastic depth) while the head trains.
        if self.transfer_enabled and not self._backbone_unfrozen:
            backbone = self._backbone_module()
            if backbone is not None:
                backbone.eval()

        if len(self.train_loader) == 0:
            msg = (
                "Training data loader is empty (0 batches). "
                "Please check dataset path, split file, "
                "and batch size/drop_last settings."
            )
            self.logger.error(msg)
            raise RuntimeError(msg)

        # Create asynchronous prefetch stream
        prefetch_stream = None
        if self.prefetch_to_gpu:
            prefetch_stream = torch.cuda.Stream(device=self.device)

        # Track B UDA: cycle an unlabeled target-domain iterator alongside the
        # source loader (single-frame conditions only; sequence models feed cached
        # features and are excluded). Inactive by default -> no behavioural change.
        self._coral_active = (
            self.coral_weight > 0
            and self.target_train_loader is not None
            and not self.is_sequence_model
        )
        target_iter = iter(self.target_train_loader) if self._coral_active else None
        if self._coral_active:
            self.logger.info(
                "UDA CORAL active: coral_weight=%s, target batches=%s",
                self.coral_weight, len(self.target_train_loader),
            )

        # Initialize data iterator and prefetch first batch
        data_iter = iter(self.train_loader)
        next_batch = self._prefetch_batch(data_iter, prefetch_stream)
        if next_batch is None:
            msg = (
                "Unable to fetch batches from training loader; "
                "please verify the data pipeline."
            )
            self.logger.error(msg)
            raise RuntimeError(msg)

        # Initialize variables for tracking
        accum_count: int = 0
        epoch_loss: float = 0.0
        all_predictions = []
        all_targets = []

        # Progress bar for the epoch
        pbar = tqdm(
            range(len(self.train_loader)), 
            desc=f"Epoch {self.epoch+1}/{self.epochs} [Train]"
        )
        for batch_idx in pbar:
            batch = next_batch
            if batch is None:
                break
            # Wait for prefetching to complete
            if prefetch_stream is not None:
                torch.cuda.current_stream(self.device).wait_stream(prefetch_stream)
            # Prefetch next batch
            if batch_idx + 1 < len(self.train_loader):
                next_batch = self._prefetch_batch(data_iter, prefetch_stream)
            else:
                # Final batch - set to None to avoid unnecessary fetching
                next_batch = None

            images = batch['image']
            targets = batch['force']

            # Fetch (and cycle) an unlabeled target-domain batch for CORAL.
            tgt_images = None
            if target_iter is not None:
                try:
                    tgt_batch = next(target_iter)
                except StopIteration:
                    target_iter = iter(self.target_train_loader)
                    tgt_batch = next(target_iter)
                tgt_images = tgt_batch['image'].to(self.device, non_blocking=True)

            if accum_count == 0:
                self.optimizer.zero_grad(set_to_none=True)

            if self.use_amp:
                with autocast(device_type=self.device.type, dtype=self.amp_dtype):
                    outputs, loss = self._forward_loss(images, targets, tgt_images)
                    loss = loss / self.grad_accum_steps

                grad_scaler = self.grad_scaler
                if grad_scaler is None:
                    raise RuntimeError(
                        "GradScaler is not initialised while AMP is enabled."
                    )
                grad_scaler.scale(loss).backward()

                accum_count += 1
                if accum_count == self.grad_accum_steps or batch_idx == len(self.train_loader) - 1:
                    grad_scaler.step(self.optimizer)
                    grad_scaler.update()
                    accum_count = 0
            else:
                outputs, loss = self._forward_loss(images, targets, tgt_images)
                loss = loss / self.grad_accum_steps
                loss.backward()

                accum_count += 1
                if accum_count == self.grad_accum_steps or batch_idx == len(self.train_loader) - 1:
                    self.optimizer.step()
                    accum_count = 0

            epoch_loss += loss.item() * self.grad_accum_steps
            all_predictions.append(self._final_pred(outputs).detach().cpu().float())
            all_targets.append(targets.detach().cpu().float())

            pbar.set_postfix({"loss": loss.item() * self.grad_accum_steps})

            if self.empty_cache_freq > 0 and batch_idx % self.empty_cache_freq == 0 and batch_idx > 0:
                # Avoid synchronizing in the hot training loop to reduce stalls.
                self._cleanup_memory(synchronize=False)

        if not all_predictions:
            msg = (
                "No training batches were processed in this epoch;"
                " aborting training loop."
            )
            self.logger.error(msg)
            raise RuntimeError(msg)

        # Every batch size should be equal, or used drop_last=True
        epoch_loss /= len(all_predictions)
        all_predictions = torch.cat(all_predictions, dim=0)
        all_targets = torch.cat(all_targets, dim=0)

        # Calculate metrics for the epoch
        metrics = self._compute_metrics(all_predictions, all_targets)
        metrics['loss'] = epoch_loss

        if self.supports_component_monitoring:
            if 'loss_magnitude_component' in metrics:
                self.loss_component_history['train_magnitude_loss'].append(metrics['loss_magnitude_component'])
            if 'loss_angle_component' in metrics:
                self.loss_component_history['train_angle_loss'].append(metrics['loss_angle_component'])

        self.visualizer.update(metrics, self.epoch, prefix="train_")

        self.train_metrics_history.append(metrics)

        self.logger.info(self._format_epoch_summary("Train", epoch_loss, metrics))

        return metrics

    def validate(self):
        """Validate the model on the validation dataset"""
        # Set model to evaluation mode
        self.model.eval()
        
        val_loss: float = 0.0
        all_predictions = []
        all_targets = []
        
        # Progress bar
        pbar = tqdm(
            self.val_loader, 
            desc=f"Epoch {self.epoch+1}/{self.epochs} [Val]"
        )
        with torch.no_grad():
            for batch_idx, batch in enumerate(pbar):
                images = batch["image"].to(self.device, non_blocking=True)
                targets = batch["force"].to(self.device, non_blocking=True)
                
                with autocast(
                    device_type=self.device.type,
                    dtype=self.amp_dtype,
                    enabled=self.use_amp,
                ):
                    outputs = self.model(images)
                    loss = self.loss_fn(outputs, targets)

                val_loss += loss.item()
                all_predictions.append(self._final_pred(outputs).detach().cpu().float())
                all_targets.append(targets.detach().cpu().float())

                pbar.set_postfix({"loss": loss.item()})
        
        # End-of-validation cleanup can synchronize to reclaim cache deterministically.
        self._cleanup_memory(synchronize=True)
        
        # Need to check if every batch size is equal
        val_loss /= len(self.val_loader)
        all_predictions = torch.cat(all_predictions, dim=0)
        all_targets = torch.cat(all_targets, dim=0)
        
        metrics = self._compute_metrics(all_predictions, all_targets)
        metrics["loss"] = val_loss

        if self.supports_component_monitoring:
            if 'loss_magnitude_component' in metrics:
                self.loss_component_history['val_magnitude_loss'].append(metrics['loss_magnitude_component'])
            if 'loss_angle_component' in metrics:
                self.loss_component_history['val_angle_loss'].append(metrics['loss_angle_component'])
        
        self.visualizer.update(metrics, self.epoch, prefix="val_")
        
        self.val_metrics_history.append(metrics)
        
        self.logger.info(self._format_epoch_summary("Val", val_loss, metrics))
        
        if (self.epoch + 1) % 10 == 0:  # Every 10 epochs
            try:
                # Create directory for distance histogram visualizations
                dist_dir = os.path.join(self.exp_output_dir, "visualizations", "DistanceChange")
                os.makedirs(dist_dir, exist_ok=True)
                vis_path = os.path.join(dist_dir, f"force_distance_epoch_{self.epoch+1}.png")

                # The distance histogram is per-sample; flatten the (B, T, 3)
                # sequence tensors to (B*T, 3) so frames are pooled.
                if self.is_sequence_model:
                    hist_targets = all_targets.reshape(-1, all_targets.shape[-1])
                    hist_predictions = all_predictions.reshape(-1, all_predictions.shape[-1])
                else:
                    hist_targets = all_targets
                    hist_predictions = all_predictions

                limits = plot_force_distance_histogram(
                    hist_targets,
                    hist_predictions,
                    vis_path,
                    title=f"Epoch {self.epoch+1} - Force Distance Distribution",
                    xlim=self._distance_hist_limits,
                    ylim=None,
                    return_limits=self._distance_hist_limits is None,
                )
                # X are fixed after first plot to ensure consistent axes
                if self._distance_hist_limits is None and limits is not None:
                    self._distance_hist_limits = limits
            except Exception as e:
                self.logger.warning(f"Failed to generate distance visualizations: {e}")

        self.logger.info("")
        return metrics
    
    def save_checkpoint(self, is_best=False) -> None:
        """Save the model checkpoint."""
        checkpoint = {
            "epoch": self.epoch,
            "best_epoch": self.best_epoch,
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "scheduler_state_dict": self.scheduler.state_dict() if self.scheduler else None,
            "best_val_metric": self.best_val_metric,
            "train_metrics_history": self.train_metrics_history,
            "val_metrics_history": self.val_metrics_history,
            # Save AMP scaler state when enabled
            "grad_scaler_state_dict": (
                self.grad_scaler.state_dict() if self.use_amp and self.grad_scaler else None
            ),
            # Save normalization parameters
            "normalize_forces": self.normalize_forces,
            "force_normalization": self.force_normalization,
            # Save loss component history
            "loss_component_history": self.loss_component_history,
            # Save loss function type and configuration
            "loss_type": self.loss_type,
            "supports_component_monitoring": self.supports_component_monitoring,
            # Persist loss-module state (EMA buffers + any learnable loss params,
            # e.g. uncertainty-weighting log-variances). Additive; the model-only
            # load path ignores it, so old checkpoints still load.
            "loss_state_dict": self.loss_fn.state_dict(),
        }
        
        self._persist_checkpoints(checkpoint, is_best)

    def _persist_checkpoints(self, checkpoint: dict[str, Any], is_best: bool) -> None:
        """Persist checkpoint artifacts and enforce retention policy."""
        # Save regular checkpoint unless keep_last disables epoch snapshots.
        if self.keep_last > 0:
            checkpoint_path = os.path.join(
                self.checkpoint_dir, f"checkpoint_epoch{self.epoch+1}.pth"
            )
            torch.save(checkpoint, checkpoint_path)

        # If this is the best model, also save as best_model.pth.
        if self.keep_best and is_best:
            best_path = os.path.join(self.checkpoint_dir, "best_model.pth")
            torch.save(checkpoint, best_path)
            self.logger.info(f"Saving best model, epoch {self.epoch+1}")

        # Enforce keep_last for epoch checkpoints, including keep_last=0 cleanup.
        self._cleanup_checkpoints()

    def _cleanup_checkpoints(self) -> None:
        """Enforce keep_last for checkpoint_epoch*.pth files (0 removes all)."""
        import re

        pattern = re.compile(r"^checkpoint_epoch(\d+)\.pth$")
        candidates = []
        for name in os.listdir(self.checkpoint_dir):
            match = pattern.match(name)
            if match:
                candidates.append((int(match.group(1)), name))

        if len(candidates) <= self.keep_last:
            return

        candidates.sort(key=lambda x: x[0])
        to_remove = candidates[: max(len(candidates) - self.keep_last, 0)]
        for _, name in to_remove:
            try:
                os.remove(os.path.join(self.checkpoint_dir, name))
            except OSError as e:
                self.logger.warning(f"Failed to remove old checkpoint {name}: {e}")
    
    def _init_wandb(self):
        """Optionally start a Weights & Biases run (opt-in via config['wandb']).

        Behavior-preserving: when the config has no 'wandb' block or its
        'enabled' is false this is a no-op. Any failure (import/network/auth)
        is swallowed with a warning so experiment tracking can never abort a
        multi-day GPU run. The run dir lives under the per-experiment output
        dir so parallel folds never share W&B state.
        """
        self.wandb_run = None
        wb = (self.config.get("wandb") or {})
        if not wb.get("enabled"):
            return
        try:
            import wandb
            self.wandb_run = wandb.init(
                project=wb.get("project", "kidknet"),
                entity=wb.get("entity"),
                group=wb.get("group"),
                name=wb.get("name", self.experiment_name),
                dir=self.exp_output_dir,
                config=self.config,
                mode=wb.get("mode", "online"),
            )
            self.logger.info(
                f"W&B tracking enabled: project={wb.get('project')} "
                f"group={wb.get('group')} name={wb.get('name', self.experiment_name)}"
            )
        except Exception as e:  # noqa: BLE001
            self.wandb_run = None
            self.logger.warning(f"W&B init failed ({e}); continuing without tracking.")

    def _wandb_log_epoch(self, train_metrics, val_metrics, epoch_time):
        """Stream one epoch's train/val metrics + LR to W&B (no-op if disabled)."""
        if not self.wandb_run:
            return
        try:
            payload = {
                "epoch": self.epoch + 1,
                "epoch_time_sec": epoch_time,
                "best_val_loss": self.best_val_metric,
                "lr": self.optimizer.param_groups[0]["lr"],
            }
            for k, v in (train_metrics or {}).items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    payload[f"train/{k}"] = v
            for k, v in (val_metrics or {}).items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    payload[f"val/{k}"] = v
            self.wandb_run.log(payload, step=self.epoch)
        except Exception as e:  # noqa: BLE001
            self.logger.warning(f"W&B log failed ({e}); continuing.")

    def _finish_wandb(self):
        """Record best-epoch summary and close the W&B run (no-op if disabled)."""
        if not self.wandb_run:
            return
        try:
            self.wandb_run.summary["best_epoch"] = self.best_epoch + 1
            self.wandb_run.summary["best_val_loss"] = self.best_val_metric
            if self.val_metrics_history:
                for k, v in self.val_metrics_history[self.best_epoch].items():
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        self.wandb_run.summary[f"best/val/{k}"] = v
            self.wandb_run.finish()
        except Exception as e:  # noqa: BLE001
            self.logger.warning(f"W&B finish failed ({e}); continuing.")
        finally:
            self.wandb_run = None

    def train(self):
        """Main training loop"""
        self.logger.info(f"Starting training for {self.epochs} epochs")
        
        # Start memory monitoring
        monitor_started = False
        if self.memory_monitor:
            self.memory_monitor.start()
            monitor_started = True
            self.logger.info("Memory monitoring started")
        
        total_epoch_time = 0.0
        timed_epochs = 0
        try:
            for epoch in range(self.epoch, self.epochs):
                self.epoch = epoch
                epoch_start_time = time.time()

                # Transfer (cond4): unfreeze the backbone once the probe ends.
                self._apply_transfer_phase(epoch)

                # Train and validate
                train_metrics = self.train_epoch()
                val_metrics = self.validate()
                
                # Step the LR scheduler
                if self.scheduler:
                    if isinstance(self.scheduler, ReduceLROnPlateau):
                        self.scheduler.step(val_metrics["loss"])
                    else:
                        self.scheduler.step()
                
                # Track per-epoch timing
                epoch_time = time.time() - epoch_start_time
                total_epoch_time += epoch_time
                timed_epochs += 1
                
                # Check for new best model
                current_val_metric = val_metrics["loss"]
                is_best = current_val_metric < self.best_val_metric
                
                if is_best:
                    self.best_val_metric = current_val_metric
                    self.best_epoch = self.epoch
                    
                # Log timing stats
                avg_epoch_time = total_epoch_time / max(timed_epochs, 1)
                estimated_remaining = (self.epochs - self.epoch - 1) * avg_epoch_time
                self.logger.info(f"Epoch {self.epoch+1}: {epoch_time:.1f}s, "
                               f"Avg: {avg_epoch_time:.1f}s/epoch, "
                               f"ETA: {estimated_remaining/60:.1f}min")
                
                # Save checkpoint
                self.save_checkpoint(is_best)

                # Stream this epoch's metrics to W&B (no-op if disabled)
                self._wandb_log_epoch(train_metrics, val_metrics, epoch_time)
                
                # Early stopping
                if (self.epoch - self.best_epoch) >= self.early_stopping_patience:
                    self.logger.info(f"Early stopping triggered at epoch {self.epoch+1}")
                    break
            
            try:
                self.visualizer.plot_comprehensive_training_progress()
            except Exception as e:
                self.logger.warning(f"Failed to plot final training progress: {e}")
            
            self.logger.info(f"Training completed. Best validation performance at epoch {self.best_epoch+1}")
            return self.val_metrics_history[self.best_epoch]
        finally:
            if monitor_started and self.memory_monitor:
                self.memory_monitor.stop()
                self.logger.info("Memory monitoring stopped")
            self._finish_wandb()
