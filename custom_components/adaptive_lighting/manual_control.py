"""Manual overrides with independent direct and native-group contributions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .adaptation_utils import LightControlAttributes

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True)
class ManualOverrideReset:
    """Describe cleared history, changed flags and source provenance released."""

    cleared_entities: frozenset[str]
    affected_entities: frozenset[str]
    affected_owners: frozenset[str] = frozenset()
    released_entities: frozenset[str] = frozenset()


@dataclass
class _GroupOverride:
    """One profile's subgroup pause, including its surviving member contributions."""

    members: set[str]
    attributes: LightControlAttributes
    original_members: frozenset[str]


class ManualOverrideState:
    """Own direct flags and subgroup provenance without HA lifecycle effects.

    ``direct`` remains a mutable dictionary for existing manager consumers.
    A derived subgroup pause belongs to its requesting profile and applies to
    the subgroup itself and its members. It never becomes an independent flag.
    """

    def __init__(self) -> None:
        """Start without direct overrides or inherited contributions."""
        self.direct: dict[str, LightControlAttributes] = {}
        self._sources: dict[tuple[str, str], _GroupOverride] = {}

    def effective(self, light: str) -> LightControlAttributes:
        """Return the union of direct and inherited attributes for a light."""
        attributes = self.direct.get(light, LightControlAttributes.NONE)
        for (_, group), source in self._sources.items():
            if light == group or light in source.members:
                attributes |= source.attributes
        return attributes

    def owned_entities(self, *, owner: str | None = None) -> set[str]:
        """Return source groups and surviving members requiring lifecycle tracking."""
        entities: set[str] = set()
        for (profile, group), source in self._sources.items():
            if owner is None or profile == owner:
                entities.add(group)
                entities.update(source.members)
        return entities

    def set_direct(
        self,
        light: str,
        attributes: LightControlAttributes,
    ) -> set[str]:
        """Replace direct attributes without changing inherited contributions."""
        self.direct[light] = attributes
        return {light}

    def add_direct(
        self,
        light: str,
        attributes: LightControlAttributes,
    ) -> set[str]:
        """Add only the requested attributes to the independent override."""
        return self.set_direct(
            light,
            self.direct.get(light, LightControlAttributes.NONE) | attributes,
        )

    def replace_source(
        self,
        group: str,
        members: Iterable[str],
        attributes: LightControlAttributes,
        *,
        owner: str,
    ) -> set[str]:
        """Replace this profile's subgroup pause, preserving other sources."""
        key = (owner, group)
        member_ids = set(members)
        affected = {group} | member_ids
        if previous := self._sources.get(key):
            affected.update(previous.members)
        self._sources[key] = _GroupOverride(
            member_ids,
            attributes,
            frozenset(member_ids),
        )
        return affected

    def clear_owner(
        self,
        owner: str,
        *,
        within_members: Iterable[str] | None = None,
    ) -> ManualOverrideReset:
        """Release a profile's pauses, optionally limited to a requested parent group.

        Original membership retains reset scope even after explicit member
        resets have removed every inherited contribution from a subgroup.
        """
        scope = None if within_members is None else set(within_members)
        previously_owned = self.owned_entities()
        groups = set()
        affected = set()
        for key, source in tuple(self._sources.items()):
            if key[0] == owner and (
                scope is None
                or (source.original_members and source.original_members <= scope)
            ):
                groups.add(key[1])
                affected.update(source.members)
                self._sources.pop(key)
        affected.update(groups)
        cleared = frozenset(group for group in groups if not self.effective(group))
        return ManualOverrideReset(
            cleared,
            frozenset(affected),
            frozenset({owner}) if groups else frozenset(),
            frozenset(previously_owned - self.owned_entities()),
        )

    def clear(
        self,
        lights: Iterable[str],
        *,
        source_owner: str | None = None,
    ) -> ManualOverrideReset:
        """Clear direct flags and matching derived contributions for these lights.

        Explicitly named reset entities clear every contribution. Profile resets
        and implicit descendants of a native parent protect another profile's
        sources; the longstanding global policy for direct flags is unchanged.
        """
        cleared = frozenset(lights)
        previously_owned = self.owned_entities()
        affected = set(cleared)
        owners = set()
        for light in cleared:
            self.direct[light] = LightControlAttributes.NONE
        for key, source in tuple(self._sources.items()):
            owner, group = key
            if source_owner is not None and owner != source_owner:
                continue
            if group in cleared:
                owners.add(owner)
                affected.update(source.members)
                self._sources.pop(key)
            else:
                if source.members & cleared:
                    owners.add(owner)
                source.members.difference_update(cleared)
        return ManualOverrideReset(
            cleared,
            frozenset(affected),
            frozenset(owners),
            frozenset(previously_owned - self.owned_entities()),
        )

    def expire(self, light: str) -> ManualOverrideReset:
        """Release expired contributions, including their final subgroup pause."""
        keys = [key for key, source in self._sources.items() if light in source.members]
        previously_owned = self.owned_entities()
        change = self.clear([light])
        cleared = set(change.cleared_entities)
        affected = set(change.affected_entities)
        for key in keys:
            if (source := self._sources.get(key)) is not None and not source.members:
                self._sources.pop(key)
                group = key[1]
                affected.add(group)
                if not self.effective(group):
                    cleared.add(group)
        return ManualOverrideReset(
            frozenset(cleared),
            frozenset(affected),
            change.affected_owners,
            frozenset(previously_owned - self.owned_entities()),
        )

    def forget(self, lights: Iterable[str]) -> ManualOverrideReset:
        """Retire entities, clearing contributions and removing their raw keys."""
        change = self.clear(lights)
        for light in change.cleared_entities:
            self.direct.pop(light, None)
        return change
