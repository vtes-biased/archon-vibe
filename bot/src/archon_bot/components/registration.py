"""Registration components — VEKN ID choice buttons and modals.

These are defined in commands/player.py as miru Views/Modals for co-location
with the command logic. This module re-exports them for external use.
"""

from ..commands.player import VeknChoiceView, VeknIdModal

__all__ = ["VeknChoiceView", "VeknIdModal"]
