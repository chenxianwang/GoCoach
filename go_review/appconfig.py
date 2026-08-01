"""Shared, safe configuration loader.

Secrets (e.g. the ikatago username/password) must NOT live in a tracked file.
The real settings live in `config.json` (git-ignored, machine-local).  A clone
without one falls back to `config.example.json`, and any `${ENV_VAR}` in string
values is expanded from the environment — so credentials can be supplied via
IKATAGO_USERNAME / IKATAGO_PASSWORD instead of being written to disk.
"""

import os
import json

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_PATH = os.path.join(HERE, "config.json")
EXAMPLE_PATH = os.path.join(HERE, "config.example.json")


def config_path():
    """Prefer the local config.json; fall back to the committed example."""
    return REAL_PATH if os.path.exists(REAL_PATH) else EXAMPLE_PATH


def _expand(v):
    """Expand ${ENV} and ~ in strings, recursively through lists/dicts."""
    if isinstance(v, str):
        return os.path.expanduser(os.path.expandvars(v))
    if isinstance(v, list):
        return [_expand(x) for x in v]
    if isinstance(v, dict):
        return {k: _expand(x) for k, x in v.items()}
    return v


def load_config(path=None):
    p = path or config_path()
    with open(p, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return {k: _expand(v) for k, v in cfg.items()}
