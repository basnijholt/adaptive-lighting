"""Utility functions for HA core."""
from collections.abc import Awaitable
from typing import Callable

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.util.read_only_dict import ReadOnlyDict

from .adaptation_utils import ServiceData


def setup_service_call_interceptor(
    hass: HomeAssistant,
    domain: str,
    service: str,
    intercept_func: Callable[[ServiceCall, ServiceData], Awaitable[None] | None],
) -> Callable[[], None]:
    """Inject a function into a registered service call to preprocess service data.

    The injected interceptor function receives the service call and a writeable data dictionary
    (the data of the service call is read-only) before the service call is executed."""
    try:
        # HACK: Access protected attribute of HA service registry.
        # This is necessary to replace a registered service handler with our
        # proxy handler to intercept calls.
        registered_services = (
            hass.services._services  # pylint: disable=protected-access
        )
    except AttributeError as error:
        raise RuntimeError(
            "Intercept failed because registered services are no longer accessible "
            "(internal API may have changed)"
        ) from error

    if domain not in registered_services or service not in registered_services[domain]:
        raise RuntimeError(
            f"Intercept failed because service {domain}.{service} is not registered"
        )

    existing_service = registered_services[domain][service]

    async def service_func_proxy(call: ServiceCall) -> None:
        # Convert read-only data to writeable dictionary for modification by interceptor
        data = dict(call.data)

        # Call interceptor
        await intercept_func(call, data)

        # Convert data back to read-only
        call.data = ReadOnlyDict(data)

        # Call original service handler with processed data
        await existing_service.job.target(call)

    hass.services.async_register(
        domain, service, service_func_proxy, existing_service.schema
    )

    def remove():
        # Remove the interceptor by reinstalling the original service handler
        hass.services.async_register(
            domain, service, existing_service.job.target, existing_service.schema
        )

    return remove
