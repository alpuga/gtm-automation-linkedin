"""Shared LinkedIn page helpers."""

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


def find_profile_action(profile_card, name: str):
    """Find a profile action by name — LinkedIn uses both <a> and <button>."""
    for role in ("link", "button"):
        el = profile_card.get_by_role(role, name=name)
        try:
            if el.first.is_visible(timeout=2000):
                return el.first
        except PlaywrightTimeoutError:
            pass
    return None
