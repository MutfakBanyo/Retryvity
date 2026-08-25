"""The About screen: product identity, authorship, and an optional
progressive-disclosure environment summary.

Fully static/offline — the only network-capable action here is opening an
external link (website/Instagram), and that happens strictly on explicit
user click via ``QDesktopServices.openUrl``, never automatically and
never during construction/startup. See docs/BRANDING.md for the identity
this consumes (all sourced from ``core/product.py`` — never hardcode
name/version/author text in a widget).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFormLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from corona_doctor.core.models import EnvironmentReport
from corona_doctor.core.product import (
    AUTHOR_INSTAGRAM_LABEL,
    AUTHOR_INSTAGRAM_URL,
    AUTHOR_NAME,
    AUTHOR_WEBSITE_LABEL,
    AUTHOR_WEBSITE_URL,
    PRODUCT_NAME,
    PRODUCT_TAGLINE,
    PRODUCT_VERSION_DISPLAY,
)
from corona_doctor.ui.branding import load_brand_pixmap
from corona_doctor.ui.design.colors import Color
from corona_doctor.ui.design.metrics import Spacing

_LOGO_SIZE = 56


class _LinkLabel(QLabel):
    """One clickable link. Opens the URL only in response to an explicit
    click — never on hover, never automatically."""

    def __init__(self, text: str, url: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._url = url
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setText(f'<a href="{url}" style="color:{Color.ACCENT}; text-decoration:none;">{text}</a>')
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.setOpenExternalLinks(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("Secondary")
        self.linkActivated.connect(self._open)

    def _open(self, _href: str) -> None:
        QDesktopServices.openUrl(QUrl(self._url))


class AboutView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.SM)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        logo_label = QLabel(self)
        logo_label.setPixmap(load_brand_pixmap(_LOGO_SIZE))
        logo_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(logo_label)

        name_label = QLabel(PRODUCT_NAME, self)
        name_label.setObjectName("Title")
        name_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(name_label)

        tagline_label = QLabel(PRODUCT_TAGLINE, self)
        tagline_label.setObjectName("Secondary")
        tagline_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(tagline_label)

        version_label = QLabel(PRODUCT_VERSION_DISPLAY, self)
        version_label.setObjectName("Caption")
        version_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(version_label)

        root.addSpacing(Spacing.MD)

        author_surface = QWidget(self)
        author_surface.setObjectName("SurfaceRaised")
        author_layout = QVBoxLayout(author_surface)
        author_layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        author_layout.setSpacing(Spacing.XS)
        author_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        developed_by = QLabel(f"Developed by {AUTHOR_NAME}", author_surface)
        developed_by.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        author_layout.addWidget(developed_by)

        website_link = _LinkLabel(AUTHOR_WEBSITE_LABEL, AUTHOR_WEBSITE_URL, author_surface)
        author_layout.addWidget(website_link, alignment=Qt.AlignmentFlag.AlignHCenter)

        instagram_link = _LinkLabel(AUTHOR_INSTAGRAM_LABEL, AUTHOR_INSTAGRAM_URL, author_surface)
        author_layout.addWidget(instagram_link, alignment=Qt.AlignmentFlag.AlignHCenter)

        root.addWidget(author_surface)

        root.addSpacing(Spacing.SM)

        self._env_toggle = QPushButton("Show environment details", self)
        self._env_toggle.setObjectName("Secondary")
        self._env_toggle.setCheckable(True)
        self._env_toggle.toggled.connect(self._on_env_toggle)
        root.addWidget(self._env_toggle)

        self._env_surface = QWidget(self)
        self._env_surface.setObjectName("Surface")
        self._env_form = QFormLayout(self._env_surface)
        self._env_form.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        self._env_form.setSpacing(Spacing.SM)
        self._env_rows: dict[str, QLabel] = {}
        for field in ("3ds Max", "Corona", "Python", "Qt"):
            value = QLabel("—", self._env_surface)
            self._env_form.addRow(field, value)
            self._env_rows[field] = value
        self._env_surface.setVisible(False)
        root.addWidget(self._env_surface)

        root.addStretch(1)

    def _on_env_toggle(self, checked: bool) -> None:
        self._env_surface.setVisible(checked)
        self._env_toggle.setText("Hide environment details" if checked else "Show environment details")

    def show_environment(self, report: EnvironmentReport) -> None:
        self._env_rows["3ds Max"].setText(report.max_version)
        self._env_rows["Corona"].setText(
            "Detected" if report.corona_detected else ("Not detected" if report.corona_detected is False else "unknown")
        )
        self._env_rows["Python"].setText(report.python_version)
        self._env_rows["Qt"].setText(report.qt_version)
