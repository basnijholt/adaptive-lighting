"""Utility functions for HA core."""
import logging
from collections.abc import Awaitable, Callable

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.util.read_only_dict import ReadOnlyDict

from .adaptation_utils import ServiceData

_LOGGER = logging.getLogger(__name__)


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
            hass.services._services  # pylint: disable=protected-access
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
            await intercept_func(call, data)

            # Convert data back to read-only
            call.data = ReadOnlyDict(data)
        except Exception as e:  # noqa: BLE001
            # Blindly catch all exceptions to avoid breaking light.turn_on
            _LOGGER.error(
                "Error for call '%s' in service_func_proxy: '%s'",
                call.data,
                e,
            )
        # Call original service handler with processed data
        await existing_service.job.target(call)

    hass.services.async_register(
        domain,
        service,
        service_func_proxy,
        existing_service.schema,
    )

    def remove():
        # Remove the interceptor by reinstalling the original service handler
        hass.services.async_register(
            domain,
            service,
            existing_service.job.target,
            existing_service.schema,
        )

    return remove
