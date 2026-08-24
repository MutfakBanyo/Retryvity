"""Host adapters: the only place allowed to import pymxs/qtmax/Corona.

Every module in this package follows the same shape::

    try:
        import pymxs
    except ImportError:
        pymxs = None

so the package remains importable outside 3ds Max. Callers must always
check the adapter's availability before assuming host functionality
exists.
"""
