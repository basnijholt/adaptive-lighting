"""Utility functions for adaptation commands."""
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any, Literal

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_BRIGHTNESS_STEP,
    ATTR_BRIGHTNESS_STEP_PCT,
    ATTR_COLOR_NAME,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ATTR_RGBWW_COLOR,
    ATTR_TRANSITION,
    ATTR_XY_COLOR,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import Context, HomeAssistant, State

_LOGGER = logging.getLogger(__name__)

COLOR_ATTRS = {  # Should ATTR_PROFILE be in here?
    ATTR_COLOR_NAME,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_XY_COLOR,
    ATTR_RGBW_COLOR,
    ATTR_RGBWW_COLOR,
}


BRIGHTNESS_ATTRS = {
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_BRIGHTNESS_STEP,
    ATTR_BRIGHTNESS_STEP_PCT,
}

ServiceData = dict[str, Any]


def _split_service_call_data(service_data: ServiceData) -> list[ServiceData]:
    """Splits the service data by the adapted attributes.

    i.e., into separate data items for brightness and color.
    """
    common_attrs = {ATTR_ENTITY_ID}
    common_data = {k: service_data[k] for k in common_attrs if k in service_data}

    attributes_split_sequence = [BRIGHTNESS_ATTRS, COLOR_ATTRS]
    service_datas = []

    for attributes in attributes_split_sequence:
        split_data = {
            attribute: service_data[attribute]
            for attribute in attributes
            if service_data.get(attribute)
        }
        if split_data:
            service_datas.append(common_data | split_data)

    # Distribute the transition duration across all service calls
    if service_datas and (transition := service_data.get(ATTR_TRANSITION)) is not None:
        transition /= len(service_datas)

        for service_data in service_datas:
            service_data[ATTR_TRANSITION] = transition

    return service_datas


def _remove_redundant_attributes(
    service_data: ServiceData,
    state: State,
) -> ServiceData:
    """Filter service data by removing attributes that already equal the given state.

    Removes all attributes from service call data whose values are already present
    in the target entity's state.
    """
    return {
        k: v
        for k, v in service_data.items()
        if k not in state.attributes or v != state.attributes[k]
    }


def _has_relevant_service_data_attributes(service_data: ServiceData) -> bool:
    """Determines whether the service data justifies an adaptation service call.

    A service call is not justified for data which does not contain any entries that
    change relevant attributes of an adapting entity, e.g., brightness or color.
    """
    common_attrs = {ATTR_ENTITY_ID, ATTR_TRANSITION}

    return any(attr not in common_attrs for attr in service_data)


async def _create_service_call_data_iterator(
    hass: HomeAssistant,
    service_datas: list[ServiceData],
    filter_by_state: bool,
) -> AsyncGenerator[ServiceData, None]:
    """Enumerates and filters a list of service datas on the fly.

    If filtering is enabled, every service data is filtered by the current state of
    the related entity and only returned if it contains relevant data that justifies
    a service call.
    The main advantage of this generator over a list is that it applies the filter
    at the time when the service data is read instead of up front. This gives greater
    flexibility because entity states can change while the items are iterated.
    """
    for service_data in service_datas:
        if filter_by_state and (entity_id := service_data.get(ATTR_ENTITY_ID)):
            current_entity_state = hass.states.get(entity_id)

            # Filter data to remove attributes that equal the current state
            if current_entity_state is not None:
                service_data = _remove_redundant_attributes(  # noqa: PLW2901
                    service_data,
                    state=current_entity_state,
                )

            # Emit service data if it still contains relevant attributes (else try next)
            if _has_relevant_service_data_attributes(service_data):
                yield service_data
        else:
            yield service_data


@dataclass
class AdaptationData:
    """Holds all data required to execute an adaptation."""

    entity_id: str
    context: Context
    sleep_time: float
    service_call_datas: AsyncGenerator[ServiceData, None]
    force: bool
    max_length: int
    which: Literal["brightness", "color", "both"]
    initial_sleep: bool = False

    async def next_service_call_data(self) -> ServiceData | None:
        """Return data for the next service call, or none if no more data exists."""
        return await anext(self.service_call_datas, None)


class NoColorOrBrightnessInServiceDataError(Exception):
    """Exception raised when no color or brightness attributes are found in service data."""


def _identify_lighting_type(
    service_data: ServiceData,
) -> Literal["brightness", "color", "both"]:
    """Extract the 'which' attribute from the service data."""
    has_brightness = ATTR_BRIGHTNESS in service_data
    has_color = any(attr in service_data for attr in COLOR_ATTRS)
    if has_brightness and has_color:
        return "both"
    if has_brightness:
        return "brightness"
    if has_color:
        return "color"
    msg = f"Invalid service_data, no brightness or color attributes found: {service_data=}"
    raise NoColorOrBrightnessInServiceDataError(msg)


def prepare_adaptation_data(
    hass: HomeAssistant,
    entity_id: str,
    context: Context,
    transition: float | None,
    split_delay: float,
    service_data: ServiceData,
    split: bool,
    filter_by_state: bool,
    force: bool,
) -> AdaptationData:
    """Prepares a data object carrying all data required to execute an adaptation."""
    _LOGGER.debug(
        "Preparing adaptation data for %s with service data %s",
        entity_id,
        service_data,
    )
    service_datas = _split_service_call_data(service_data) if split else [service_data]

    service_datas_length = len(service_datas)

    if transition is not None:
        transition_duration_per_data = transition / max(1, service_datas_length)
        sleep_time = transition_duration_per_data + split_delay
    else:
        sleep_time = split_delay

    service_data_iterator = _create_service_call_data_iterator(
        hass,
        service_datas,
        filter_by_state,
    )

    lighting_type = _identify_lighting_type(service_data)

    return AdaptationData(
        entity_id=entity_id,
        context=context,
        sleep_time=sleep_time,
        service_call_datas=service_data_iterator,
        force=force,
        max_length=service_datas_length,
        which=lighting_type,
    )
