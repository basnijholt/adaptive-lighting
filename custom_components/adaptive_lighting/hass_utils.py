"""Utility functions for HA core."""

import logging
from collections.abc import Awaitable, Callable

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry, entity_registry
from homeassistant.util.read_only_dict import ReadOnlyDict

from .adaptation_utils import ServiceData

_LOGGER = logging.getLogger(__name__)


def area_entities(hass: HomeAssistant, area_id: str):
    """Get all entities linked to an area."""
    ent_reg = entity_registry.async_get(hass)
    entity_ids = [
        entry.entity_id
        for entry in entity_registry.async_entries_for_area(ent_reg, area_id)
    ]
    dev_reg = device_registry.async_get(hass)
    entity_ids.extend(
        [
            entity.entity_id
            for device in device_registry.async_entries_for_area(dev_reg, area_id)
            for entity in entity_registry.async_entries_for_device(ent_reg, device.id)
            if entity.area_id is None
        ],
    )
    return entity_ids


def setup_service_call_interceptor(
    hass: HomeAssistant,
    domain: str,
    service: str,
    intercept_func: Callable[[ServiceCall, ServiceData], Awaitable[None] | None],
) -> Callable[[], None]:
    """Inject a function into a registered service call to preprocess service data.

    The injected interceptor function receives the service call and a writeable data dictionary
    (the data of the service call is read-only) before the service call is executed.
    """
    try:
        # HACK: Access protected attribute of HA service registry.
        # This is necessary to replace a registered service handler with our
        # proxy handler to intercept calls.
        registered_services = (
            hass.services._services  # pylint: disable=protected-access  # type: ignore[attr-defined]
        )
    except AttributeError as error:
        msg = (
            "Intercept failed because registered services are no longer"
            " accessible (internal API may have changed)"
        )
        raise RuntimeError(msg) from error

    if domain not in registered_services or service not in registered_services[domain]:
        msg = f"Intercept failed because service {domain}.{service} is not registered"
        raise RuntimeError(msg)

    existing_service = registered_services[domain][service]

    async def service_func_proxy(call: ServiceCall) -> None:
        try:
            # Convert read-only data to writeable dictionary for modification by interceptor
            data = dict(call.data)

            # Call interceptor
            result = intercept_func(call, data)
            if result is not None:
                await result

            # Convert data back to read-only
            call.data = ReadOnlyDict(data)
        except Exception:
            # Blindly catch all exceptions to avoid breaking light.turn_on
            _LOGGER.exception(
                "Error for call '%s' in service_func_proxy",
                call.data,
            )
        # Call original service handler with processed data
        import asyncio

        target = existing_service.job.target
        if asyncio.iscoroutinefunction(target):
            await target(call)
        else:
            target(call)

    hass.services.async_register(
        domain,
        service,
        service_func_proxy,
        existing_service.schema,
    )

    def remove() -> None:
        # Remove the interceptor by reinstalling the original service handler
        hass.services.async_register(
            domain,
            service,
            existing_service.job.target,
            existing_service.schema,
        )

    return remove
