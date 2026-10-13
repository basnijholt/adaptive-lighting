"""Native request snapshots and completed-invocation retention contracts."""

import gc
import weakref
from unittest.mock import Mock

import pytest
from homeassistant.components.adaptive_lighting.adaptation_utils import (
    LightControlAttributes,
)
from homeassistant.components.adaptive_lighting.native_group_models import (
    AttributePolicy,
    BatchExecution,
    NativeIntent,
    NativePlan,
)
from homeassistant.core import Context


@pytest.mark.parametrize(
    ("attribute", "vector"),
    [
        ("rgb_color", [255, 56, 0]),
        ("xy_color", [0.4, 0.3]),
        ("hs_color", [30, 75]),
        ("rgbw_color", [255, 56, 0, 80]),
        ("rgbww_color", [255, 56, 0, 80, 100]),
    ],
)
def test_colour_intent_detaches_mutable_colour_vectors(attribute, vector):
    """Queued colour is fixed even when the preparation payload changes later."""
    expected = tuple(vector)
    source = {attribute: vector, "transition": 1}
    intent = NativeIntent(
        colour=source,
        explicit=LightControlAttributes.NONE,
        version=0,
        source="light.member",
        policies={LightControlAttributes.COLOR: AttributePolicy(Mock(), 0)},
    )

    source["transition"] = 2
    vector[0] = 0
    dispatch = dict(intent.colour)
    dispatch[attribute] = tuple(0 for _ in vector)

    assert intent.colour[attribute] == expected
    assert intent.colour["transition"] == 1
    with pytest.raises(TypeError):
        intent.colour[attribute][0] = 0


def test_complete_request_snapshot_detaches_scene_colour_vectors():
    """Later scene payload edits cannot change the request used for child matching."""
    colour = [255, 56, 0]
    request = {"state": "on", "rgb_color": colour}
    requests = {"light.member": request}
    plan = NativePlan(Context(), requests, {}, {})

    colour[0] = 0
    request["state"] = "off"
    requests.clear()

    assert plan.requests["light.member"] == {
        "state": "on",
        "rgb_color": (255, 56, 0),
    }


def test_closed_execution_releases_error_traceback_payload():
    """A late-report claim retaining outcomes must not retain failed request frames."""
    execution = BatchExecution()

    class RequestPayload:
        """Stand in for request data reachable through a failed handler frame."""

    def fail_request():
        raise ValueError

    def record_failure():
        payload = RequestPayload()
        reference = weakref.ref(payload)
        try:
            fail_request()
        except ValueError as error:
            execution.errors.append(error)
        return reference

    reference = record_failure()
    gc.collect()
    assert reference() is not None

    execution.close()
    gc.collect()

    assert execution.closed
    assert reference() is None
