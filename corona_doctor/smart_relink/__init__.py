"""Smart Asset Recovery — upgrades Missing Texture Relink from "browse to
the exact file" into "search a library, score candidates, review, then
relink through the existing Repair Engine". See
docs/SMART_RELINK.md for the full architecture.

Pure domain (``models.py``/``index.py``/``scoring.py``/``session.py``/
``providers.py``) has no Qt/pymxs import — every filesystem/network call
is either injected or lives in the UI/devtools layer, matching
``repair/``'s discipline (see docs/REPAIR_ENGINE.md).
"""

from __future__ import annotations
