"""Core domain layer: diagnostic engine, rule engine, result model, events.

Nothing in ``corona_doctor.core`` may import pymxs, PySide6, qtmax or any
other host-bound module. This package must remain importable in a plain
Python 3.11 interpreter so it can be unit tested outside 3ds Max.
"""
