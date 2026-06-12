"""Workspace-anchored path resolution.

The MedSim2Learn workspace keeps data under a single DataFlow/ root and code
in per-project directories; nothing here should hardcode a machine-specific
absolute path. Config files may use the placeholders "{workspace}" and
"{dataflow}", which expand to the workspace root and DataFlow/ respectively.
"""

import os

# Deform_post/ holds this package; its parent is the workspace root.
DEFORM_POST_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKSPACE_ROOT = os.path.dirname(DEFORM_POST_DIR)
DATAFLOW_DIR = os.path.join(WORKSPACE_ROOT, "DataFlow")
DEFORM_POST_DATA_DIR = os.path.join(DATAFLOW_DIR, "Deform_post")


def expand(path):
    """Expand {workspace}/{dataflow} placeholders and normalize separators."""
    if path is None:
        return None
    s = str(path)
    s = s.replace("{workspace}", WORKSPACE_ROOT)
    s = s.replace("{dataflow}", DATAFLOW_DIR)
    return os.path.normpath(s)
