"""Abstract interfaces for CRM integrations."""

from abc import ABC, abstractmethod


class LeadSource(ABC):
    @abstractmethod
    def fetch_leads(self) -> list[dict]:
        """Fetch all contactable leads."""
        ...


class ActivityLogger(ABC):
    @abstractmethod
    def log_activity(self, email: str, result: str, linkedin_url: str = "") -> None:
        """Log a LinkedIn action for a lead."""
        ...
