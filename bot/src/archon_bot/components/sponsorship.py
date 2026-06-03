"""Sponsorship components — approve/deny buttons for new player sponsorship.

These are defined in commands/player.py as miru Views for co-location
with the command logic. This module re-exports them for external use.
"""

from ..commands.player import SponsorshipModal, SponsorshipView

__all__ = ["SponsorshipModal", "SponsorshipView"]
