"""Narrow package boundary for the Hybrid Kernel service image.

Service processes import their explicit ASGI modules.  Keeping this initializer
empty prevents Python from executing the repository-level Hybrid facade, whose
public convenience exports intentionally include controller policy and runner
modules.
"""
