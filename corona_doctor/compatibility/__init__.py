"""Compatibility and capability layer.

Nothing here should assume Corona properties exist; everything is queried
through :class:`~corona_doctor.compatibility.capabilities.CapabilityRegistry`
so future rules can call ``capabilities.supports(...)`` instead of guessing.
"""
