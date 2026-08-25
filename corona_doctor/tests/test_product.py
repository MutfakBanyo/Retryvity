"""Unit tests for centralized product/authorship metadata. No 3ds Max required."""

from __future__ import annotations

from corona_doctor.core import product


def test_product_identity_fields_present():
    assert product.PRODUCT_NAME == "Corona Doctor"
    assert product.AUTHOR_NAME == "Murat Yüksel"


def test_display_version_hides_prerelease_suffix():
    # v0.2.0-bootstrap-style internal strings must never leak into the
    # primary user-facing display version.
    assert product._display_version("0.2.0") == "v0.2"
    assert product._display_version("0.2.0-bootstrap") == "v0.2"
    assert product._display_version("1") == "v1"


def test_urls_use_https_and_match_labels():
    assert product.AUTHOR_WEBSITE_URL == "https://yukselmurat.com"
    assert product.AUTHOR_WEBSITE_URL.endswith(product.AUTHOR_WEBSITE_LABEL)
    assert product.AUTHOR_INSTAGRAM_URL == "https://instagram.com/yuxelmurat"
    assert product.AUTHOR_INSTAGRAM_URL.endswith(product.AUTHOR_INSTAGRAM_LABEL.lstrip("@"))


def test_display_version_matches_current_version():
    assert product.PRODUCT_VERSION_DISPLAY == "v0.2"
    assert product.PRODUCT_VERSION == "0.2.0"
