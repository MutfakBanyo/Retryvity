"""UI layer. Depends on PySide6/qtmax; never contains scene-analysis logic.

Widgets consume domain objects (Finding, EnvironmentReport, ScanSummary)
produced by core/adapters/scanners — they never reach into pymxs
themselves.
"""
