"""Pytest wrappers around the dpost module self-tests.

Each module keeps its own _self_test() next to the code it exercises (the
established pattern in this workspace); these wrappers make the whole suite
runnable via pytest as well as `python main.py selftest`.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_forces_real():
    from dpost.forces import real

    real._self_test()


def test_dataset_serialize():
    from dpost.dataset import serialize

    serialize._self_test()


def test_simrun_batch():
    from dpost.simrun import batch

    batch._self_test()


def test_replay_prep():
    from dpost import replay

    replay._self_test()


def test_artifacts():
    from dpost import artifacts

    artifacts._self_test()


def test_annotate():
    from dpost import annotate

    annotate._self_test()
    annotate._self_test_descriptors()
    annotate._self_test_zone()
    annotate._self_test_poisson()
    annotate._self_test_cli()
    annotate._self_test_annotation()


def test_assemble():
    from dpost.dataset import assemble

    assert assemble.run_self_test()
