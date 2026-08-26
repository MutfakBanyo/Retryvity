"""Tunable numeric constants for the V0.1 comparison engine.

All tolerances are expressed in 3ds Max system units. They are collected
here (rather than inlined) so a scene working at an unusual unit scale
can be diagnosed by looking at exactly one file.
"""

from __future__ import annotations

APP_NAME = "RevisionGuard"
LOG_PREFIX = "[RevisionGuard]"

# --- transform tolerances -------------------------------------------------
# Never compare transform floats with ==; a Max scene round-trips matrices
# through several float conversions and picks up noise well below these.
POSITION_TOLERANCE = 1.0e-4
ROTATION_TOLERANCE = 1.0e-5  # per quaternion component
SCALE_TOLERANCE = 1.0e-5

# --- geometry tolerances --------------------------------------------------
BBOX_TOLERANCE = 1.0e-4

# Vertex coordinates are snapped to this grid before hashing so the digest
# is stable across evaluations. Anything smaller than this is treated as
# float noise rather than a real mesh edit.
VERTEX_QUANTIZATION = 1.0e-4

# Full-mesh hashing is O(vertices) through pymxs, which is the slow part of
# a scan. Meshes above this size fall back to a deterministic strided
# sample of this many vertices (see fingerprint.build_geometry_signature).
MAX_HASHED_VERTICES = 20000

# --- scan behaviour -------------------------------------------------------
# How often the scan yields to Qt so the panel keeps repainting. pymxs is
# main-thread-only, so the scan cannot be moved off the UI thread.
UI_YIELD_INTERVAL = 25
