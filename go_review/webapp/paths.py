"""Filesystem anchor: the go_review/ directory, resolved from this package's own location."""

import os


# webapp/ is one level below go_review/, so go up twice.
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
