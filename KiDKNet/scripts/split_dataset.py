#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Dataset Splitter script
===========
This script is used to split a dataset into training, 
validation, and test sets.
"""

import os
import sys
import argparse
import logging
import yaml

# This script runs via main.py or standalone, and the path insert is required
# only when running standalone.
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from dknet.data import holdout_split_dataset


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(description="Dataset splitting tool")
    
    parser.add_argument(
        "--config", 
        type=str, 
        default="../configs/unified_config.yaml",
        help="Configuration file path"
    )
    parser.add_argument(
        "--data_dir", 
        type=str, 
        default=None,
        help="Data directory path (overrides config file)"
    )
    parser.add_argument(
        "--seed", 
        type=int, 
        default=None,
        help="Random seed (overrides config file)"
    )
    
    return parser.parse_args()

def _load_config(config_path: str) -> dict:
    """Load YAML configuration file"""
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config

def split_dataset_main(config=None) -> None:
    """
    Main function to perform dataset splitting.
    
    Args:
        config (dict, optional): Configuration dictionary. If not provided, it 
        is loaded from command-line arguments.
    """
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    if config is None:
        # Parse command-line arguments
        args = parse_args()
        
        # Load configuration file
        config = _load_config(args.config)
        
        # Override configuration with command-line arguments
        if args.data_dir:
            config["data"]["data_dir"] = args.data_dir
        
        if args.seed:
            config["general"]["seed"] = args.seed
    
    # Perform dataset splitting
    holdout_split_dataset(config)

if __name__ == "__main__":
    split_dataset_main()
