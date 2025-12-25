from __future__ import annotations

from datetime import datetime
from types import MappingProxyType
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import SOURCE_USER


class MockConfigEntry(ConfigEntry):
    """Lightweight stand-in for Home Assistant's test MockConfigEntry.

    This wraps a real ConfigEntry so the integration setup code paths stay intact.
    """

    def __init__(
        self,
        *,
        domain: str,
        data: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        title: str | None = None,
        entry_id: str | None = None,
        unique_id: str | None = None,
        source: str = SOURCE_USER,
        disabled_by: Any | None = None,
    ) -> None:
        super().__init__(
            domain=domain,
            data=data or {},
            options=options or {},
            title=title or domain,
            version=1,
            minor_version=1,
            source=source,
            pref_disable_new_entities=False,
            pref_disable_polling=False,
            discovery_keys=MappingProxyType({}),
            unique_id=unique_id,
            entry_id=entry_id,
            state=ConfigEntryState.NOT_LOADED,
            created_at=datetime.now(),
            modified_at=None,
            disabled_by=disabled_by,
        )

    def add_to_hass(self, hass: HomeAssistant) -> "MockConfigEntry":
        """Register the entry with a Home Assistant instance for tests."""
        hass.config_entries._entries[self.entry_id] = self  # type: ignore[attr-defined]
        return self
