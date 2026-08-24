"""Corona Doctor - diagnostic, optimization and repair assistant for
Autodesk 3ds Max 2026.3+ and Chaos Corona 15+.

This top-level package intentionally avoids importing any 3ds Max or Qt
bound modules so that ``corona_doctor.core`` and other Max-independent
packages remain importable in a plain Python 3.11 environment (e.g. for
unit tests running outside 3ds Max).
"""

from corona_doctor.version import __version__

__all__ = ["__version__"]
