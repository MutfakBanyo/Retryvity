"""Shared constant values used across the core domain layer."""

from __future__ import annotations

APP_NAME = "Corona Doctor"
ORG_NAME = "CoronaDoctor"
SETTINGS_NAMESPACE = "corona_doctor"

# Navigation sections planned for the finished product. Only a subset is
# active in the bootstrap phase (see ui/main_window.py); the rest are
# declared here so future milestones extend one registry instead of
# inventing a new one.
NAV_OVERVIEW = "overview"
NAV_DIAGNOSTICS = "diagnostics"
NAV_ENVIRONMENT = "environment"
NAV_SCENE = "scene"
NAV_RENDERER = "renderer"
NAV_MATERIALS = "materials"
NAV_TEXTURES = "textures"
NAV_GEOMETRY = "geometry"
NAV_LIGHTING = "lighting"
NAV_PERFORMANCE = "performance"
NAV_REPORT = "report"

ACTIVE_NAV_SECTIONS = (NAV_OVERVIEW, NAV_DIAGNOSTICS, NAV_ENVIRONMENT)
PLANNED_NAV_SECTIONS = (
    NAV_SCENE,
    NAV_RENDERER,
    NAV_MATERIALS,
    NAV_TEXTURES,
    NAV_GEOMETRY,
    NAV_LIGHTING,
    NAV_PERFORMANCE,
    NAV_REPORT,
)
