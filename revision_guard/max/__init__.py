"""3ds Max host boundary.

``scene_access`` is the only module in RevisionGuard permitted to import
pymxs. Keeping that rule is what lets revision_guard.core be imported and
tested in a plain Python interpreter.
"""
