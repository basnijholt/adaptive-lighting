"""Manual override provenance, independent of HA timers and service dispatch."""

import pytest
from homeassistant.components.adaptive_lighting.adaptation_utils import (
    LightControlAttributes as Attributes,
)
from homeassistant.components.adaptive_lighting.manual_control import (
    ManualOverrideState,
)


@pytest.mark.parametrize("independent", ["none", "before", "during"])
def test_replacing_subgroup_pause_preserves_independent_member_flags(independent):
    """Changing ALL to brightness releases only the subgroup's colour pause."""
    state = ManualOverrideState()
    if independent == "before":
        state.set_direct("light.a", Attributes.COLOR)
    state.replace_source(
        "light.group",
        ["light.a", "light.b"],
        Attributes.ALL,
        owner="profile",
    )
    if independent == "during":
        state.set_direct("light.a", Attributes.COLOR)

    affected = state.replace_source(
        "light.group",
        ["light.a", "light.b"],
        Attributes.BRIGHTNESS,
        owner="profile",
    )

    assert affected == {"light.group", "light.a", "light.b"}
    assert state.effective("light.a") == (
        Attributes.BRIGHTNESS if independent == "none" else Attributes.ALL
    )
    assert state.effective("light.b") == Attributes.BRIGHTNESS


def test_adding_direct_flag_does_not_adopt_inherited_axes():
    """A member's direct brightness change must not retain a released colour pause."""
    state = ManualOverrideState()
    state.replace_source("light.group", ["light.a"], Attributes.ALL, owner="profile")
    state.add_direct("light.a", Attributes.BRIGHTNESS)

    state.clear(["light.group"])

    assert state.effective("light.a") == Attributes.BRIGHTNESS
    assert state.direct["light.a"] == Attributes.BRIGHTNESS


def test_replacing_subgroup_membership_releases_former_members():
    """A changed subgroup affects former and current members, preserving other sources."""
    state = ManualOverrideState()
    state.replace_source(
        "light.group",
        ["light.a", "light.b"],
        Attributes.ALL,
        owner="profile",
    )
    state.replace_source("light.other", ["light.a"], Attributes.COLOR, owner="profile")

    affected = state.replace_source(
        "light.group",
        ["light.b", "light.c"],
        Attributes.BRIGHTNESS,
        owner="profile",
    )

    assert affected == {"light.group", "light.a", "light.b", "light.c"}
    assert state.effective("light.a") == Attributes.COLOR
    assert state.effective("light.b") == Attributes.BRIGHTNESS
    assert state.effective("light.c") == Attributes.BRIGHTNESS


def test_clearing_subgroup_preserves_other_sources_and_direct_flags():
    """Inherited changes notify members without resetting their independent history."""
    state = ManualOverrideState()
    state.set_direct("light.group", Attributes.ALL)
    state.set_direct("light.a", Attributes.BRIGHTNESS)
    state.replace_source(
        "light.group",
        ["light.a", "light.b"],
        Attributes.ALL,
        owner="profile",
    )
    state.replace_source("light.other", ["light.a"], Attributes.COLOR, owner="profile")

    change = state.clear(["light.group"])

    assert change.cleared_entities == {"light.group"}
    assert change.affected_entities == {"light.group", "light.a", "light.b"}
    assert state.effective("light.group") == Attributes.NONE
    assert state.effective("light.a") == Attributes.ALL
    assert state.effective("light.b") == Attributes.NONE


def test_clearing_member_does_not_clear_siblings_or_subgroup():
    """An explicit member reset clears its contributions without resetting the source."""
    state = ManualOverrideState()
    state.set_direct("light.group", Attributes.ALL)
    state.set_direct("light.a", Attributes.BRIGHTNESS)
    state.replace_source(
        "light.group",
        ["light.a", "light.b"],
        Attributes.COLOR,
        owner="profile",
    )

    change = state.clear(["light.a"])

    assert change.cleared_entities == change.affected_entities == {"light.a"}
    assert state.effective("light.a") == Attributes.NONE
    assert state.effective("light.b") == Attributes.COLOR
    assert state.effective("light.group") == Attributes.ALL


def test_last_member_expiry_also_releases_subgroup_flag():
    """A scene subgroup without its own timer expires after its final contribution."""
    state = ManualOverrideState()
    state.replace_source(
        "light.group",
        ["light.a", "light.b"],
        Attributes.ALL,
        owner="profile",
    )

    first = state.expire("light.a")
    assert first.cleared_entities == first.affected_entities == {"light.a"}
    assert first.affected_owners == {"profile"}
    assert state.effective("light.group") == Attributes.ALL
    assert state.effective("light.b") == Attributes.ALL

    last = state.expire("light.b")
    assert (
        last.cleared_entities
        == last.affected_entities
        == {
            "light.b",
            "light.group",
        }
    )
    assert state.effective("light.group") == Attributes.NONE
    assert last.affected_owners == {"profile"}


def test_forgetting_source_removes_its_raw_key_and_releases_members():
    """Retired tracking cannot leave inherited pauses on surviving lights."""
    state = ManualOverrideState()
    state.set_direct("light.group", Attributes.ALL)
    state.set_direct("light.a", Attributes.BRIGHTNESS)
    state.replace_source("light.group", ["light.a"], Attributes.COLOR, owner="profile")

    change = state.forget(["light.group"])

    assert "light.group" not in state.direct
    assert change.cleared_entities == {"light.group"}
    assert change.affected_entities == {"light.group", "light.a"}
    assert change.affected_owners == {"profile"}
    assert state.effective("light.a") == Attributes.BRIGHTNESS


def test_raw_direct_dictionary_remains_mutable_and_stable_across_resets():
    """Existing manager consumers retain the same raw mapping, without inherited flags."""
    state = ManualOverrideState()
    direct = state.direct
    direct["light.a"] = Attributes.BRIGHTNESS
    state.replace_source("light.group", ["light.a"], Attributes.COLOR, owner="profile")

    assert state.effective("light.a") == Attributes.ALL
    assert direct["light.a"] == Attributes.BRIGHTNESS

    state.clear(["light.a"])
    assert state.direct is direct
    assert direct["light.a"] == Attributes.NONE
    assert state.effective("light.a") == Attributes.NONE


@pytest.mark.parametrize("same_group", [False, True])
def test_profile_reset_preserves_foreign_source_and_independent_group_flag(same_group):
    """Overlapping source ownership cannot merge into a single raw group flag."""
    state = ManualOverrideState()
    other_group = "light.group" if same_group else "light.other"
    state.set_direct("light.group", Attributes.BRIGHTNESS)
    state.set_direct("light.a", Attributes.BRIGHTNESS)
    state.replace_source(
        "light.group",
        ["light.a", "light.b"],
        Attributes.ALL,
        owner="profile",
    )
    state.replace_source(
        other_group,
        ["light.b", "light.c"],
        Attributes.COLOR,
        owner="other",
    )

    change = state.clear_owner("profile")

    assert change.cleared_entities == set()
    assert change.affected_entities == {"light.group", "light.a", "light.b"}
    assert state.effective("light.group") == (
        Attributes.ALL if same_group else Attributes.BRIGHTNESS
    )
    assert state.effective("light.a") == Attributes.BRIGHTNESS
    assert state.effective("light.b") == Attributes.COLOR
    assert state.effective("light.c") == Attributes.COLOR

    # Whole-profile target reset retains global direct-flag semantics, but
    # cannot consume another profile's inherited member pause.
    state.clear(["light.a", "light.b"], source_owner="profile")
    assert state.effective("light.a") == Attributes.NONE
    assert state.effective("light.b") == Attributes.COLOR
    assert state.effective(other_group) == (
        Attributes.ALL if same_group else Attributes.COLOR
    )


def test_replacing_one_owner_preserves_other_owner_on_same_subgroup():
    """Changing one profile's selective pause cannot overwrite a peer's flags."""
    state = ManualOverrideState()
    state.replace_source("light.group", ["light.a"], Attributes.COLOR, owner="other")
    state.replace_source("light.group", ["light.a"], Attributes.ALL, owner="profile")
    state.replace_source(
        "light.group",
        ["light.b"],
        Attributes.BRIGHTNESS,
        owner="profile",
    )

    assert state.effective("light.group") == Attributes.ALL
    assert state.effective("light.a") == Attributes.COLOR
    assert state.effective("light.b") == Attributes.BRIGHTNESS
    state.clear_owner("other")
    assert state.effective("light.group") == Attributes.BRIGHTNESS
    assert state.effective("light.a") == Attributes.NONE


def test_source_expiry_preserves_independent_group_flag_and_other_owner():
    """An expired source cannot clear an independent group or sibling pause."""
    state = ManualOverrideState()
    state.set_direct("light.group", Attributes.BRIGHTNESS)
    state.replace_source("light.group", ["light.a"], Attributes.ALL, owner="profile")
    state.replace_source("light.group", ["light.b"], Attributes.COLOR, owner="other")

    first = state.expire("light.a")
    assert first.cleared_entities == {"light.a"}
    assert first.affected_entities == {"light.a", "light.group"}
    assert state.effective("light.group") == Attributes.ALL
    last = state.expire("light.b")
    assert last.cleared_entities == {"light.b"}
    assert last.affected_entities == {"light.b", "light.group"}
    assert state.effective("light.group") == Attributes.BRIGHTNESS


@pytest.mark.parametrize("clear_members_first", [False, True])
def test_parent_reset_uses_original_scope_and_preserves_unrelated_sources(
    clear_members_first,
):
    """Empty contributions still belong to their original, distinct parent scope."""
    state = ManualOverrideState()
    state.replace_source(
        "light.subgroup",
        ["light.a", "light.b"],
        Attributes.COLOR,
        owner="profile",
    )
    state.replace_source("light.other", ["light.c"], Attributes.ALL, owner="profile")
    state.replace_source("light.peer", ["light.a"], Attributes.ALL, owner="other")
    if clear_members_first:
        state.clear(["light.a", "light.b", "light.c"])

    state.clear_owner("profile", within_members=[])
    assert state.effective("light.subgroup") == Attributes.COLOR
    state.clear_owner("profile", within_members=["light.a"])
    assert state.effective("light.subgroup") == Attributes.COLOR
    state.clear_owner("profile", within_members=["light.a", "light.b"])

    assert state.effective("light.subgroup") == Attributes.NONE
    assert state.effective("light.other") == Attributes.ALL
    assert state.effective("light.peer") == Attributes.ALL


def test_source_ownership_follows_surviving_contributions_without_losing_reset_scope():
    """Lifecycle ownership is a view of sources, not another mutable registry."""
    state = ManualOverrideState()
    state.replace_source(
        "light.group",
        ["light.a", "light.b"],
        Attributes.ALL,
        owner="profile",
    )
    state.replace_source("light.group", ["light.c"], Attributes.COLOR, owner="other")
    assert state.owned_entities() == {
        "light.group",
        "light.a",
        "light.b",
        "light.c",
    }
    assert state.owned_entities(owner="profile") == {
        "light.group",
        "light.a",
        "light.b",
    }

    change = state.clear(["light.a", "light.b"], source_owner="profile")
    assert change.affected_owners == {"profile"}
    assert state.owned_entities(owner="profile") == {"light.group"}
    change = state.clear_owner("profile", within_members=["light.a", "light.b"])
    assert change.affected_owners == {"profile"}
    assert state.owned_entities(owner="profile") == set()
    assert state.owned_entities() == {"light.group", "light.c"}

    state.replace_source("light.group", ["light.d"], Attributes.COLOR, owner="other")
    assert state.owned_entities() == {"light.group", "light.d"}
    change = state.expire("light.d")
    assert change.affected_owners == {"other"}
    assert state.owned_entities() == set()
