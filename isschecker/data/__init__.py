"""Compliance criteria shipped with the checker.

This module exists so that the directory is a regular package rather than a
namespace package: ``importlib.resources.files()`` then resolves it to a single
concrete directory instead of a ``MultiplexedPath``.
"""
