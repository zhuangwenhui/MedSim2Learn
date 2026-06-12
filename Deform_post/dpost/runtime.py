"""Host-runtime heuristics.

The pipeline's parallelism unit is the SEQUENCE (whole subprocesses), not the
individual frame, so all this module needs is a sane default for how many
sequence processes to run side by side.
"""

import os


def default_worker_count(reserve=2):
    """Logical cores minus a reserve for the OS/render thread, at least 1."""
    cores = os.cpu_count() or 1
    return max(1, cores - reserve)
