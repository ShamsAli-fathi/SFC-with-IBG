"""Narrow package boundary for the Hybrid Kernel controller image.

The controller entry point imports its required modules explicitly.  This
initializer avoids eager service application construction and keeps image
contents, rather than the repository convenience facade, authoritative.
"""
