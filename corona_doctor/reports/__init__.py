"""Human-readable, production-safe report formatters.

Separate from ``devtools/`` on purpose: everything here is safe to show a
user (no raw Python repr, no AnimHandle diagnostics, no adapter-internal
dumps) — see ``reports/texture_report.py`` and docs/TEXTURE_DOCTOR.md,
"Production result model".
"""

from __future__ import annotations
