"""Tests for Adaptive Lighting HASS utils."""

import asyncio
from contextvars import ContextVar
from inspect import signature
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.adaptive_lighting.adaptation_utils import ServiceData
from homeassistant.components.adaptive_lighting.hass_utils import (
    setup_service_call_interceptor,
)
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.const import SERVICE_TURN_ON
from homeassistant.core import ServiceCall, SupportsResponse, callback
from homeassistant.util.read_only_dict import ReadOnlyDict


@pytest.fixture
def ignore_translations_for_mock_domains():
    """Synthetic test services have no integration translation files."""
    return ["test"]


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


async def test_service_interceptor_isolates_concurrent_dispatch_calls(hass):
    """Awaited preprocessing cannot exchange data between split target calls."""
    entered = asyncio.Event()
    observed = []

    async def original(call):
        observed.append((call.data["target"], call.data["prepared"]))

    async def before(call, data):
        if data["target"] == "left":
            await entered.wait()
        else:
            entered.set()
        data["prepared"] = data["target"]

    async def around(call, invoke_original):
        await asyncio.gather(
            *(
                invoke_original(
                    ServiceCall(
                        hass,
                        call.domain,
                        call.service,
                        {"target": target},
                        context=call.context,
                    ),
                )
                for target in ("left", "right")
            ),
        )
        assert call.data == {"target": "both"}

    hass.services.async_register("test", "split", original)
    setup_service_call_interceptor(
        hass,
        "test",
        "split",
        before,
        around_func=around,
    )
    await hass.services.async_call(
        "test",
        "split",
        {"target": "both"},
        blocking=True,
    )
    assert sorted(observed) == [("left", "left"), ("right", "right")]


@pytest.mark.parametrize("failure", [None, "original", "after"])
async def test_service_interceptor_around_order_and_errors(hass, failure):
    """Wrap preprocessing and dispatch without retrying a failed original call."""
    events = []
    original_error = ValueError("original failure")
    after_error = ValueError("after failure")

    async def original(call):
        events.append(("original", dict(call.data)))
        if failure == "original":
            raise original_error
        return {"result": "original response"}

    async def before(call, data):
        events.append(("before", dict(call.data)))
        data["changed"] = True

    async def around(call, invoke_original):
        events.append(("enter", dict(call.data)))
        try:
            result = await invoke_original()
            events.append(("after", result))
            if failure == "after":
                raise after_error
            return result
        finally:
            events.append(("exit", None))

    hass.services.async_register(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        original,
        supports_response=SupportsResponse.OPTIONAL,
    )
    setup_service_call_interceptor(
        hass,
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        before,
        around_func=around,
    )
    if failure:
        with pytest.raises(ValueError, match="failure") as exc_info:
            await hass.services.async_call(
                LIGHT_DOMAIN,
                SERVICE_TURN_ON,
                {"initial": True},
                blocking=True,
                return_response=True,
            )
        assert exc_info.value is (
            original_error if failure == "original" else after_error
        )
    else:
        assert await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {"initial": True},
            blocking=True,
            return_response=True,
        ) == {"result": "original response"}
    expected = [
        ("enter", {"initial": True}),
        ("before", {"initial": True}),
        ("original", {"initial": True, "changed": True}),
    ]
    if failure != "original":
        expected.append(("after", {"result": "original response"}))
    assert events == [*expected, ("exit", None)]


@pytest.mark.parametrize("fail_inner", [False, True])
async def test_service_interceptor_nested_context_cleanup(hass, fail_inner):
    """Nested awaited services inherit their outer operation and clean up errors."""
    current_operation = ContextVar("test_operation", default=())
    events = []
    inner_error = ValueError("inner failure")

    async def original(call):
        events.append((call.service, current_operation.get()))
        if call.service == "outer":
            await hass.services.async_call(
                "test",
                "inner",
                {},
                blocking=True,
                context=call.context,
            )
            events.append(("outer_resumed", current_operation.get()))
        elif fail_inner:
            raise inner_error

    async def around(call, invoke_original):
        token = current_operation.set((*current_operation.get(), call.service))
        try:
            return await invoke_original()
        finally:
            current_operation.reset(token)
            events.append((f"{call.service}_cleanup", current_operation.get()))

    for service in ("outer", "inner"):
        hass.services.async_register("test", service, original)
        setup_service_call_interceptor(
            hass,
            "test",
            service,
            lambda _call, _data: None,
            around_func=around,
        )
    if fail_inner:
        with pytest.raises(ValueError, match="inner failure") as exc_info:
            await hass.services.async_call("test", "outer", {}, blocking=True)
        assert exc_info.value is inner_error
    else:
        await hass.services.async_call("test", "outer", {}, blocking=True)
    expected = [
        ("outer", ("outer",)),
        ("inner", ("outer", "inner")),
        ("inner_cleanup", ("outer",)),
    ]
    if not fail_inner:
        expected.append(("outer_resumed", ("outer",)))
    assert events == [*expected, ("outer_cleanup", ())]
    assert current_operation.get() == ()


async def test_service_interceptor_cancellation_cleans_up_once(hass):
    """Cancellation unwinds the around hook without dispatching a second call."""
    entered = asyncio.Event()
    events = []

    async def original(_call):
        events.append("original")
        entered.set()
        await asyncio.Event().wait()

    async def around(_call, invoke_original):
        try:
            return await invoke_original()
        finally:
            events.append("cleanup")

    hass.services.async_register("test", "cancel", original)
    setup_service_call_interceptor(
        hass,
        "test",
        "cancel",
        lambda _call, _data: None,
        around_func=around,
    )
    task = asyncio.create_task(
        hass.services.async_call("test", "cancel", {}, blocking=True),
    )
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert events == ["original", "cleanup"]


async def test_service_interceptor_removal_keeps_external_replacement(hass):
    """Unloading must not reinstall an obsolete handler over another owner."""
    original, replacement, before = AsyncMock(), AsyncMock(), AsyncMock()
    hass.services.async_register(LIGHT_DOMAIN, SERVICE_TURN_ON, original)
    remove = setup_service_call_interceptor(
        hass,
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        before,
    )
    hass.services.async_register(LIGHT_DOMAIN, SERVICE_TURN_ON, replacement)

    remove()
    remove()
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {},
        blocking=True,
    )

    replacement.assert_awaited_once()
    original.assert_not_called()
    before.assert_not_called()


async def test_service_interceptor_preserves_metadata_and_sync_response(hass):
    """Installing and removing preserve service metadata and callback responses."""
    descriptions = {"name": "Original service"}
    metadata = (
        {"description_placeholders": descriptions}
        if "description_placeholders"
        in signature(hass.services.async_register).parameters
        else {}
    )
    observed = []

    @callback
    def original(call):
        observed.append(dict(call.data))
        return {"response": call.data["request"]}

    hass.services.async_register(
        "test",
        "respond",
        original,
        supports_response=SupportsResponse.ONLY,
        **metadata,
    )
    remove = setup_service_call_interceptor(
        hass,
        "test",
        "respond",
        lambda _call, _data: None,
    )
    for remove_first in (False, True):
        if remove_first:
            remove()
        service = hass.services.async_services()["test"]["respond"]
        assert service.supports_response is SupportsResponse.ONLY
        if metadata:
            assert service.description_placeholders == descriptions
        assert await hass.services.async_call(
            "test",
            "respond",
            {"request": "unchanged"},
            blocking=True,
            return_response=True,
        ) == {"response": "unchanged"}
    assert observed == [{"request": "unchanged"}] * 2
