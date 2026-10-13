"""Utility functions for HA core."""

import logging
from collections.abc import Awaitable, Callable
from inspect import isawaitable
from typing import Any, Protocol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse
from homeassistant.helpers.target import async_extract_referenced_entity_ids
from homeassistant.util.read_only_dict import ReadOnlyDict

try:
    from homeassistant.helpers.target import TargetSelection
except ImportError:  # Compatibility with older Home Assistant releases
    from homeassistant.helpers.target import TargetSelectorData as TargetSelection

from .adaptation_utils import ServiceData

_LOGGER = logging.getLogger(__name__)


class ServiceContinuation(Protocol):
    """Invoke the original handler, optionally with an independent target call."""

    def __call__(
        self,
        dispatch_call: ServiceCall | None = None,
    ) -> Awaitable[ServiceResponse]:
        """Dispatch once, preserving its response and exception."""
        ...


def target_entities(
    hass: HomeAssistant,
    service_data: ServiceData,
    *,
    expand_group: bool = False,
) -> set[str]:
    """Resolve selected entities, optionally expanding HA helper groups."""
    selected = async_extract_referenced_entity_ids(
        hass,
        TargetSelection(service_data),
        expand_group=expand_group,
    )
    return selected.referenced | selected.indirectly_referenced


def setup_service_call_interceptor(
    hass: HomeAssistant,
    domain: str,
    service: str,
    intercept_func: Callable[[ServiceCall, ServiceData], Awaitable[None] | None],
    *,
    around_func: (
        Callable[[ServiceCall, ServiceContinuation], Awaitable[ServiceResponse]] | None
    ) = None,
) -> Callable[[], None]:
    """Inject a function into a registered service call to preprocess service data.

    The injected interceptor function receives the service call and a writeable data dictionary
    (the data of the service call is read-only) before the service call is executed.
    The optional around function wraps both preprocessing and original dispatch,
    and must invoke the supplied continuation to execute them. The continuation
    accepts an optional independent ServiceCall for concurrent target dispatch.
    Exceptions from
    the around function or original service propagate without retrying dispatch.
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

    async def service_func_proxy(call: ServiceCall) -> ServiceResponse:
        async def invoke_original(
            dispatch_call: ServiceCall | None = None,
        ) -> ServiceResponse:
            dispatch_call = call if dispatch_call is None else dispatch_call
            try:
                # Copy read-only data for modification by the interceptor.
                data = dict(dispatch_call.data)
                result = intercept_func(dispatch_call, data)
                if result is not None:
                    await result
                dispatch_call.data = ReadOnlyDict(data)
            except Exception:
                # Keep the existing fail-open behavior for preprocessing only.
                _LOGGER.exception(
                    "Error for call '%s' in service_func_proxy",
                    dispatch_call.data,
                )

            result = existing_service.job.target(dispatch_call)
            if isawaitable(result):
                return await result
            return result

        if around_func is not None:
            return await around_func(call, invoke_original)
        return await invoke_original()

    metadata: dict[str, Any] = {
        "supports_response": existing_service.supports_response,
    }
    if hasattr(existing_service, "description_placeholders"):
        metadata["description_placeholders"] = existing_service.description_placeholders

    hass.services.async_register(
        domain,
        service,
        service_func_proxy,
        existing_service.schema,
        **metadata,
    )

    def remove() -> None:
        # A later registration belongs to another owner; leave it in place.
        current = registered_services.get(domain, {}).get(service)
        if current is None or current.job.target is not service_func_proxy:
            return
        hass.services.async_register(
            domain,
            service,
            existing_service.job.target,
            existing_service.schema,
            **metadata,
        )

    return remove
