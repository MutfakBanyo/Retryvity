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


def show_corona_doctor_about() -> None:
    """Show (or focus) the panel and switch it to the About section.

    The "About Corona Doctor" menu command's target — see
    ``maxscript/helpers.ms``'s ``CoronaDoctor_About`` macroScript. Safe to
    call repeatedly, and safe to call before the panel has ever been
    opened this session (launches it first).
    """

    from corona_doctor.app.application import show_about

    show_about()


if __name__ == "__main__":  # pragma: no cover - manual/host invocation only
    show_corona_doctor()
