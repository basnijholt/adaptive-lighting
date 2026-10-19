"""Native device models separating physical colour, reports and group traffic."""

# pylint: disable=protected-access
from dataclasses import dataclass
from typing import ClassVar

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_TRANSITION,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.util.color import color_temperature_kelvin_to_mired

# Older supported Home Assistant releases do not export this attribute name.
ATTR_GROUP_ENTITIES = "group_entities"

GROUP = "light.native_group"
LEFT = "light.native_left"
RIGHT = "light.native_right"
OFF_MEMBER = "light.native_off_member"
TARGET_KELVIN = 3000


def command_params(params):
    """Omit only a proven redundant legacy alias from the command trace."""
    recorded = dict(params)
    if (kelvin := recorded.get(ATTR_COLOR_TEMP_KELVIN)) is not None and recorded.get(
        "color_temp",
    ) == color_temperature_kelvin_to_mired(kelvin):
        recorded.pop("color_temp", None)
    return recorded


class NativeMember(LightEntity):
    """A real HA light whose cached and physical colour may differ.

    A native group colour command updates the advertised cache even for OFF
    bulbs, while their physical colour remains unchanged. A bare turn-on then
    exposes that cache, reproducing the observed MQTT/native-group behaviour.
    """

    _attr_should_poll = False
    _attr_supported_color_modes: ClassVar = {ColorMode.COLOR_TEMP}
    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_min_color_temp_kelvin = 2000
    _attr_max_color_temp_kelvin = 6500
    _attr_supported_features = LightEntityFeature.TRANSITION

    def __init__(self, entity_id):
        """Start with an optimistic target cache and stale physical colour."""
        self.entity_id = entity_id
        self._attr_name = entity_id
        self._attr_is_on = False
        self._attr_brightness = 110
        self._attr_color_temp_kelvin = TARGET_KELVIN
        self.physical_kelvin = 4000

    async def async_turn_on(self, **kwargs):
        """Apply explicitly requested attributes and retain cached bare ON."""
        self._attr_is_on = True
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            self.physical_kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            self._attr_color_temp_kelvin = self.physical_kelvin
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):  # noqa: ARG002
        """Switch off without changing the retained physical attributes."""
        self._attr_is_on = False
        self.async_write_ha_state()


class NativeGroup(NativeMember):
    """A native group keeps one command target and publishes HA membership."""

    def __init__(self, members):
        """Publish members independently of the command target."""
        super().__init__(GROUP)
        self.members = members
        self._attr_is_on = True

    @property
    def extra_state_attributes(self):
        """Expose HA's native integration-group membership attribute."""
        return {ATTR_GROUP_ENTITIES: [member.entity_id for member in self.members]}

    async def async_turn_on(self, **kwargs):
        """Model group colour broadcasts updating optimistic member caches."""
        # With a lit group, a CT-only update leaves OFF members off. Brightness
        # or a bare power command can power all members, so tests catch unsafe
        # group-wide repair of an individual member's activation.
        changes_power = ATTR_BRIGHTNESS in kwargs or kwargs.keys() <= {ATTR_TRANSITION}
        if changes_power:
            self._attr_is_on = True
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            self._attr_color_temp_kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            self.physical_kelvin = self._attr_color_temp_kelvin
        for member in self.members:
            if changes_power:
                member._attr_is_on = True
            if ATTR_BRIGHTNESS in kwargs:
                member._attr_brightness = kwargs[ATTR_BRIGHTNESS]
            if ATTR_COLOR_TEMP_KELVIN in kwargs:
                member._attr_color_temp_kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
                if member.is_on:
                    member.physical_kelvin = member._attr_color_temp_kelvin
            member.async_write_ha_state()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):  # noqa: ARG002
        """One native OFF broadcast changes every member, with independent reports."""
        for member in self.members:
            member._attr_is_on = False
            member.async_write_ha_state()
        self._attr_is_on = False
        self.async_write_ha_state()


@dataclass
class NativeSetup:
    """The profile and modeled devices used by each isolated regression."""

    entry: object
    switch: object
    group: NativeGroup
    left: NativeMember
    right: NativeMember
    off_member: NativeMember


class RecordingMember(NativeMember):
    """Record every device command, regardless of who issues the service call."""

    def __init__(self, entity_id, commands):
        """Keep one shared device-boundary trace for ordering assertions."""
        super().__init__(entity_id)
        self.commands = commands
        self.attempts = []
        self.hold_reports = False
        self.before_turn_on = None

    async def async_turn_on(self, **kwargs):
        """Distinguish attempted commands from those the device actually applies."""
        command = {
            "target": self.entity_id,
            "service": "turn_on",
            **command_params(kwargs),
        }
        self.attempts.append(command)
        if self.before_turn_on is not None:
            callback, self.before_turn_on = self.before_turn_on, None
            await callback()
        await super().async_turn_on(**kwargs)
        self.commands.append(command)

    async def async_turn_off(self, **kwargs):
        """Record explicit power intent as well as colour and brightness."""
        command = {"target": self.entity_id, "service": "turn_off", **kwargs}
        self.attempts.append(command)
        await super().async_turn_off(**kwargs)
        self.commands.append(command)

    def async_write_ha_state(self):
        """Optionally delay a real ON report until after scene dispatch finishes."""
        if not self.hold_reports:
            super().async_write_ha_state()


class RecordingGroup(NativeGroup):
    """Record native broadcasts without miscounting them as member commands."""

    def __init__(self, members, commands):
        """Use the same native-group physical and optimistic-cache model."""
        super().__init__(members)
        self.commands = commands

    async def async_turn_on(self, **kwargs):
        """One native group call represents one outgoing group command."""
        self.commands.append(
            {
                "target": self.entity_id,
                "service": "turn_on",
                **command_params(kwargs),
            },
        )
        await super().async_turn_on(**kwargs)

    async def async_turn_off(self, **kwargs):
        """Record one group power command without inventing member unicasts."""
        self.commands.append(
            {"target": self.entity_id, "service": "turn_off", **kwargs},
        )
        await super().async_turn_off(**kwargs)


@dataclass
class SceneSetup:
    """The modeled native group and a trace captured after setup traffic."""

    switch: object
    group: RecordingGroup
    members: list[RecordingMember]
    commands: list[dict]

    @property
    def colour_commands(self):
        """Count scene commands and adaptive corrections equally."""
        return [call for call in self.commands if ATTR_COLOR_TEMP_KELVIN in call]
