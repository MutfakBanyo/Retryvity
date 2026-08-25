"""Online asset search — architecture + query builder for this milestone.
See docs/SMART_RELINK.md, "Online search" for why no provider actually
makes a network call yet: every implementation requires an API key
Corona Doctor cannot invent, so each provider correctly reports
``is_available() == False`` until a user configures one (env var — see
each provider class). No HTML scraping, no undocumented endpoints.

``OnlineAssetSearchProvider`` is the seam a real provider plugs into;
the core application depends only on this Protocol, never on one
specific website — see ``list_providers()``.
"""

from __future__ import annotations

import ntpath
import os
import re
from dataclasses import dataclass
from typing import Protocol

from corona_doctor.smart_relink.models import MissingAsset

# Words too generic/short to carry search signal, and common
# workstation-path noise words that should never leak into a query even
# though they might appear in a folder name (e.g. "Users", "My").
_STOP_WORDS = {
    "a", "an", "the", "of", "and", "or", "for",
    "final", "copy", "new", "old", "v1", "v2", "v3", "temp", "tmp",
}


class OnlineAssetSearchProvider(Protocol):
    """A provider never receives a local filesystem path — only the
    privacy-safe query text from ``build_privacy_safe_query`` (see
    docs/SMART_RELINK.md, "Privacy-safe query generation")."""

    name: str

    def is_available(self) -> bool:
        ...

    def search(self, query: str, *, limit: int = 10) -> list["OnlineCandidate"]:
        ...


@dataclass(frozen=True)
class OnlineCandidate:
    """An online search result — never a recovered original (see
    docs/SMART_RELINK.md, "Local recovery vs. online replacement").
    ``license_info`` is surfaced verbatim from the provider, never
    inferred."""

    title: str
    thumbnail_url: str
    source_url: str
    provider: str
    width: int | None = None
    height: int | None = None
    license_info: str = "unknown — verify with the source before use"


class _CredentialGatedProvider:
    """Shared shape for a provider that requires an API key this
    codebase does not (and will not) hardcode. ``env_var`` is checked at
    construction; ``search()`` on an unavailable provider raises rather
    than silently returning nothing, so a caller can't mistake
    "not configured" for "found zero results"."""

    name = "unnamed"
    env_var = ""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or (os.environ.get(self.env_var) if self.env_var else None)

    def is_available(self) -> bool:
        return bool(self._api_key)

    def search(self, query: str, *, limit: int = 10) -> list[OnlineCandidate]:
        if not self.is_available():
            raise RuntimeError(f"{self.name} is not configured — set {self.env_var} to enable it.")
        # Real HTTP call intentionally not implemented this milestone —
        # there is no credential available to develop or test against.
        # The architecture (this class, the Protocol, the query builder,
        # the UI's "unavailable until configured" state) is the
        # deliverable; see docs/SMART_RELINK.md, "Online search —
        # architecture + first implementation".
        raise NotImplementedError(f"{self.name} search is not implemented yet — architecture only, see docs/SMART_RELINK.md.")


class UnsplashProvider(_CredentialGatedProvider):
    name = "Unsplash"
    env_var = "CORONA_DOCTOR_UNSPLASH_API_KEY"


class PexelsProvider(_CredentialGatedProvider):
    name = "Pexels"
    env_var = "CORONA_DOCTOR_PEXELS_API_KEY"


def list_providers() -> list[OnlineAssetSearchProvider]:
    """Every provider Corona Doctor knows about — the UI lists all of
    them (labeling unavailable ones as such), never assumes exactly one
    exists. Add a new provider here, nowhere else."""

    return [UnsplashProvider(), PexelsProvider()]


def _split_words(text: str) -> list[str]:
    # camelCase / snake_case / kebab-case / spaces -> separate words.
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    words = re.split(r"[_\-\s]+", spaced)
    return [w.lower() for w in words if w and not w.isdigit() and len(w) > 1 and w.lower() not in _STOP_WORDS]


def build_privacy_safe_query(missing: MissingAsset, *, material_name: str | None = None, map_name: str | None = None) -> str:
    """Search terms built ONLY from the filename stem and the immediate
    parent folder name (plus, if given, the material/map name) — never
    the full local path, never a drive letter, never a username or
    project name. See docs/SMART_RELINK.md, "Privacy-safe query
    generation" and ``tests/test_smart_relink_providers.py`` for the
    regression guard proving a real Windows user-profile path never
    leaks through."""

    filename_stem = missing.filename.rsplit(".", 1)[0]
    parent_folder = ntpath.basename(ntpath.dirname(ntpath.normpath(missing.old_path)))

    words: list[str] = []
    words.extend(_split_words(filename_stem))
    words.extend(_split_words(parent_folder))
    if material_name:
        words.extend(_split_words(material_name))
    if map_name:
        words.extend(_split_words(map_name))

    seen: dict[str, None] = {}
    for word in words:
        seen.setdefault(word, None)
    return " ".join(seen)
