# Training entry is centralized via KiDKNet/main.py;
# avoid running this module directly.
from __future__ import annotations

import os
import yaml
import json
import torch
import logging
from datetime import datetime
import re
import sys

from dknet.data import get_dataloaders
from dknet.models import build_model
from dknet.trainers import ForceTrainer


def _fmt_metric(value: object, precision: int = 4) -> str:
    """Format numeric metrics safely."""
    try:
        return f"{float(value):.{precision}f}"  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(value)


def _sanitize_experiment_name(name: str) -> str:
    """Return a filesystem-safe experiment name across platforms."""
    # Replace characters that are invalid on Windows and problematic on POSIX.
    safe = re.sub(r'[<>:"/\\\\|?*\x00-\x1f]', "_", name)
    # Windows also disallows trailing dots/spaces in path segments.

    return safe.rstrip(" .")

def _create_experiment_name(config: dict) -> str:
    """Create an experiment name based on configuration parameters."""
    # Timestamp is influenced by the JST timezone set in main.py.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = "KiDKNet"

    # Construct suffix based on model and loss type
    backbone_config = config['model']['backbone']
    if not isinstance(backbone_config, dict):
        raise TypeError(
            "Backbone configuration must be a dictionary; " \
            "please check model.backbone settings."
        )

    backbone_name = backbone_config['name']
    if 'config' in backbone_config:
        size = backbone_config['config'].get('size')
        if size is not None:
            backbone_name = f"{backbone_name}_{size}"
    # Sequence models prepend "seq" and the temporal module type so experiment
    # names stay distinct when racing tcn/gru/transformer variants.
    if config['model'].get('name') == 'sequence_forcenet':
        temporal_type = config['model'].get('temporal', {}).get('type', 'tcn')
        backbone_name = f"seq_{backbone_name}_{temporal_type}"

    loss_config = config['training']['loss']
    loss_type = str(loss_config['type']).upper()
    if loss_type in ("COMBINED", "SEQUENCE_COMBINED"):
        lambda_mag = loss_config['lambda_magnitude']
        mag_dist = loss_config['magnitude_distance']
        angle_dist = loss_config['angle_distance']
        loss_suffix = f"{loss_type}:{lambda_mag:.1f}{mag_dist}_{1-lambda_mag:.1f}{angle_dist}"
        if loss_config.get('normalize_losses'):
            loss_suffix += "_lnorm"
        suffix = f"{backbone_name}_{loss_suffix}"
    elif loss_type == "MSE":
        suffix = f"{backbone_name}_{loss_type}"
    else:
        raise ValueError(
            f"Unsupported loss type for experiment naming: {loss_type}"
        )

    return _sanitize_experiment_name(f"{base_name}_{suffix}_{timestamp}")

def _log_training_setup_summary(
    config: dict, experiment_name: str, logger: logging.Logger
) -> None:
    """Record training setup summary to logger."""
    logger.info("=" * 60)
    logger.info("                   TRAINING SETUP SUMMARY")
    logger.info("=" * 60)

    logger.info(f"Experiment Name: {experiment_name}")
    logger.info(" ")

    backbone_config = config['model']['backbone']
    if isinstance(backbone_config, dict):
        backbone_name = backbone_config.get('name')
        backbone_params = backbone_config.get('config')
        logger.info(f"Model Backbone: {backbone_name}")
        if backbone_params:
            logger.info(f"    Backbone Config: {backbone_params}")
            logger.info(" ")
    else:
        raise TypeError(
            "Backbone configuration must be a dictionary; " \
            "please check model.backbone settings."
        )

    loss_config = config['training']['loss']
    loss_type = loss_config.get('type').upper()
    logger.info(f"Loss Function: {loss_type}")

    if loss_type == "COMBINED":
        logger.info(
            f"    Lambda Magnitude: {loss_config.get('lambda_magnitude')}"
        )
        logger.info(
            f"    Normalize Losses: {loss_config.get('normalize_losses')}"
        )
        logger.info(
            f"    Magnitude Distance: {loss_config.get('magnitude_distance')}"
        )
        logger.info(
            f"    Angle Distance: {loss_config.get('angle_distance')}"
        )
    logger.info(" ")

    train_config = config['training']
    logger.info(f"Training Epochs: {train_config.get('epochs')}")
    logger.info(f"Batch Size: {train_config.get('batch_size')}")
    logger.info(
        f"Learning Rate: {train_config.get('optimizer').get('learning_rate')}"
    )
    logger.info(
        f"Optimizer: {train_config.get('optimizer').get('type')}"
    )

    data_config = config['data']
    logger.info(f"Data Directory: {data_config.get('data_dir')}")
    
    logger.info("=" * 60)

def _save_config(config: dict, output_dir: str) -> None:
    """
    Save configuration to output directory 
    for reproducibility and evaluation.
    """
    with open(os.path.join(output_dir, 'experimentConfig.yaml'), 'w') as f:
        yaml.dump(config, f)

def prepare_datasets(config: dict, logger: logging.Logger, split_file=None):
    """Prepare datasets and data loaders for training and validation."""
    logger.info("Preparing datasets...")
    if split_file:
        logger.info(f"Using provided split file: {split_file}")
        logger.info(" ")
    else:
        raise ValueError(
            "Split file must be generated before training. " \
            "Please run split_dataset.py to create the split file."
        )

    try:
        # Create data loaders (dataset already handled in get_dataloaders)
        train_loader, val_loader, _ = get_dataloaders(config, split_file=split_file)

        return train_loader, val_loader

    except ValueError as e:
        if "split_ratios" in str(e):
            logger.error(f"Configuration error: {e}")
            logger.error(
                "Please check your configuration file and " \
                "ensure all required parameters are properly set."
            )
            sys.exit(1)
        else:
            raise
    except FileNotFoundError as e:
        if "metadata" in str(e).lower():
            logger.error(f"Dataset error: {e}")
            logger.error(
                "Please ensure the dataset has been " \
                "properly preprocessed by Deform_post"
            )
            sys.exit(1)
        else:
            raise
    except Exception as e:
        logger.error(f"Unexpected error during data preparation: {e}")
        logger.error(
            "Please check your data directory and configuration settings."
        )
        sys.exit(1)


def main(args, config=None):
    # Configuration must be provided by KiDKNet/main.py
    if config is None:
        print()
        raise ValueError(
            "Config must be provided by KiDKNet/main.py; " \
            "please check the config path."
        )  

    # Create experiment directory
    # Default experiment directory: outputs/experiments/{experiment_name}
    output_dir = config['general']['output_dir']
    experiment_name = _create_experiment_name(config)
    experiment_dir = os.path.join(output_dir, experiment_name)
    os.makedirs(experiment_dir, exist_ok=True)

    logger = logging.getLogger('train')

    # Record training setup summary
    _log_training_setup_summary(config, experiment_name, logger)

    # Seed covers model init, DataLoader shuffling, and Dropout.
    random_seed = config['general']['seed']
    torch.manual_seed(random_seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(random_seed)

    _save_config(config, experiment_dir)
    try:
        train_loader, val_loader = prepare_datasets(
            config, logger, args.split_file
        )
    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Failed to prepare datasets: {e}")
        logger.error(
            "Training cannot continue without valid data. " \
            "Please check your configuration and data setup."
        )
        sys.exit(1)
    # Model creation
    try:
        backbone_config = config['model']['backbone']
        if isinstance(backbone_config, dict):
            backbone_name = backbone_config.get('name')
        else:
            raise TypeError(
                "Backbone configuration must be a dictionary; " \
                "please check your model configuration."
            )

        logger.info(f"Creating model: backbone={backbone_name}")
        model = build_model(config['model'])

        # Record model information
        total_params = sum(p.numel() for p in model.parameters())
        trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
        logger.info(f"Model created successfully")
        logger.info(f"    Total parameters: {total_params:,}")
        logger.info(f"    Trainable parameters: {trainable_params:,}")

    except Exception as e:
        logger.error(f"Failed to create model: {e}")
        logger.error("Please check your model configuration.")
        sys.exit(1)
    # Trainer setup
    try:
        logger.info("Setting up trainer...")
        logger.info(" ")
        trainer = ForceTrainer(
            model=model,
            train_loader=train_loader,
            val_loader=val_loader,
            config=config,
            experiment_name=experiment_name,
            experiment_dir=experiment_dir,
        )

        # Record trainer configuration information
        loss_type = config['training']['loss'].get("type", "MSE").upper()
        logger.info(f"Trainer setup completed:")
        logger.info(f"    Loss function: {loss_type}")
        logger.info(
            f"    Supports component monitoring: {trainer.supports_component_monitoring}"
        )
        logger.info(f"    Visualization: enabled")
        logger.info(
            f"    Memory monitoring: {'enabled' if trainer.memory_monitor else 'disabled'}"
        )

    except Exception as e:
        logger.error(f"Failed to setup trainer: {e}")
        sys.exit(1)

    try:
        logger.info(f"Output directory: {experiment_dir}")
        logger.info(f"Starting training process...")
        logger.info(" ")

        best_metrics = trainer.train()

        completion_report = {
            "experiment_name": experiment_name,
            "training_completed": True,
            "best_epoch": trainer.best_epoch + 1,
            "total_epochs_trained": trainer.epoch + 1,
            "best_validation_metrics": best_metrics,
            "model_info": {
                "backbone": backbone_name,
                "total_parameters": total_params,
                "trainable_parameters": trainable_params
            },
            "training_config": {
                "loss_function": loss_type,
                "supports_component_monitoring": trainer.supports_component_monitoring,
                "batch_size": config.get("training", {}).get("batch_size", 32),
                "learning_rate": config.get("training", {}).get("optimizer", {}).get("learning_rate", 1e-3)
            }
        }

        with open(os.path.join(experiment_dir, 'training_completion_report.json'), 'w') as f:
            json.dump(completion_report, f, indent=4)

        logger.info("=" * 60)
        logger.info(f"Experiment: {experiment_name}")
        logger.info(f"Best epoch: {trainer.best_epoch + 1}")
        logger.info(f"Best validation loss: {_fmt_metric(best_metrics.get('loss', 'N/A'), precision=6)}")
        logger.info(
            f"Best validation accuracy@10%: "
            f"{_fmt_metric(best_metrics.get('magnitude_accuracy_10pct', 'N/A'))}"
        )

        if trainer.supports_component_monitoring:
            logger.info(f"Magnitude accuracy@10%: {_fmt_metric(best_metrics.get('magnitude_accuracy_10pct', 'N/A'))}")
            angle_acc = best_metrics.get('angle_accuracy_5deg')
            if angle_acc is not None:
                logger.info(f"Angle accuracy@5°: {_fmt_metric(angle_acc)}")

        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Training failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Return the experiment directory so orchestrators (e.g. the CV driver)
    # can locate this run's checkpoints/best_model.pth without globbing.
    return experiment_dir
