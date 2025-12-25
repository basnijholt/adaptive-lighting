"""Tests for Adaptive Lighting HASS utils."""

from unittest.mock import AsyncMock

from homeassistant.components.adaptive_lighting.adaptation_utils import ServiceData
from homeassistant.components.adaptive_lighting.hass_utils import (
    setup_service_call_interceptor,
)
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.const import SERVICE_TURN_ON
from homeassistant.core import ServiceCall
from homeassistant.util.read_only_dict import ReadOnlyDict


async def test_setup_service_call_interceptor(hass):
    """Test setup and removal of service call interceptor."""
    service_func_mock = AsyncMock()
    hass.services.async_register(LIGHT_DOMAIN, SERVICE_TURN_ON, service_func_mock)

    async def service_call():
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {},
            blocking=True,
        )

    # Test if service is called

    await service_call()
    assert service_func_mock.call_count == 1

    # Test if interceptor is called after setup

    intercept_func_mock = AsyncMock()
    remove_interceptor = setup_service_call_interceptor(
        hass,
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        intercept_func_mock,
    )

    await service_call()
    assert service_func_mock.call_count == 2
    assert intercept_func_mock.call_count == 1

    # Test if interceptor is no longer called after removal

    remove_interceptor()
    await service_call()
    assert service_func_mock.call_count == 3
    assert intercept_func_mock.call_count == 1


async def test_service_call_interceptor_data_manipulation(hass):
    """Test service call data manipulation by service call interceptor."""
    service_func_mock = AsyncMock()
    hass.services.async_register(LIGHT_DOMAIN, SERVICE_TURN_ON, service_func_mock)

    async def intercept_func(call: ServiceCall, data: ServiceData):
        data["test1"] = "changed"
        data["test2"] = "added"

    setup_service_call_interceptor(
        hass,
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        intercept_func,
    )

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {"test1": "initial"},
        blocking=True,
    )

    (service_call,) = service_func_mock.call_args[0]
    assert service_call.data == {"test1": "changed", "test2": "added"}
    assert isinstance(service_call.data, ReadOnlyDict)
