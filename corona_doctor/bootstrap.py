"""Entry point invoked by the 3ds Max menu/macroscript command.

Keep this module minimal — it exists so the host only needs one stable
import path (``corona_doctor.bootstrap``) regardless of how the internal
package layout evolves.
"""

from __future__ import annotations


def show_corona_doctor() -> None:
    """Show (or focus) the Corona Doctor panel. Safe to call repeatedly."""

    from corona_doctor.app.application import launch

    launch()


if __name__ == "__main__":  # pragma: no cover - manual/host invocation only
    show_corona_doctor()
