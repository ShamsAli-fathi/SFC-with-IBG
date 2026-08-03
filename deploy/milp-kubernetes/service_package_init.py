"""Minimal MILP package initializer used only by the service image.

Controller-facing public exports import the solver stack and are deliberately
absent from replica/forwarder/flow-generator processes.
"""
