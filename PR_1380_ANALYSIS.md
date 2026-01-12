# PR #1380 Analysis: Fix for Issue #1378

## Summary

Issue #1378 reports that in v1.30.0, lights turned on via automation are incorrectly marked as "manually controlled" and AL stops adapting them. Multiple users confirmed rolling back to v1.29.0 fixes the issue.

## Root Cause

PR #1356 ("Individual manual control of brightness and color") introduced a regression by adding a new code path in `turn_on_off_event_listener.on()` that checks for manual control on EVERY `light.turn_on` event, including when turning on from OFF state.

### The Problematic Code (added in #1356)

In `AdaptiveLightingManager.turn_on_off_event_listener`, the `on()` handler was modified to call `update_manually_controlled_from_event()` unconditionally:

```python
async def on(eid: str, event: Event) -> None:
    task = self.sleep_tasks.get(eid)
    if task is not None:
        task.cancel()
    self.turn_on_event[eid] = event

    # NEW IN #1356: This marks lights as manually controlled
    # even when turning on from OFF!
    try:
        switch = _switch_with_lights(self.hass, [eid], expand_light_groups=False)
        await self.update_manually_controlled_from_event(switch, eid, force=False)
    except NoSwitchFoundError:
        pass
```

This is incorrect because:
- When a light is OFF and you turn it on with attributes (e.g., `light.turn_on(brightness=100%)`), the intent is typically "turn on the light at this brightness" NOT "permanently override AL for brightness"
- The previous behavior (v1.29.0) only checked for manual control when the light was already ON and you changed its attributes

## The `adapt_only_on_bare_turn_on` Setting

### Documentation

From README.md:
> "If set to `true`, AL adapts only if `light.turn_on` is invoked without specifying color or brightness. This e.g., prevents adaptation when activating a scene."

### Intended Behavior

When `adapt_only_on_bare_turn_on` is enabled:
- If `light.turn_on` is called WITH color/brightness attributes → Mark as manually controlled (scene should persist)
- If `light.turn_on` is called WITHOUT attributes (bare) → Adapt normally

### Code in v1.29.0 and v1.30.0

Both versions have `_mark_manual_control_if_non_bare_turn_on` that correctly marks as manually controlled:

**v1.29.0:**
```python
def _mark_manual_control_if_non_bare_turn_on(self, entity_id, service_data):
    if any(attr in service_data for attr in COLOR_ATTRS | BRIGHTNESS_ATTRS | {ATTR_EFFECT}):
        self.mark_as_manual_control(entity_id)  # ← Marks as manually controlled
        return True
    return False
```

**v1.30.0:**
```python
def _mark_manual_control_if_non_bare_turn_on(self, entity_id, service_data):
    manual_control_attributes = get_light_control_attributes(service_data)
    if manual_control_attributes:
        self.set_manual_control_attributes(entity_id, manual_control_attributes)  # ← Marks
        return True
    return False
```

This function is called from `_respond_to_off_to_on_event` when `adapt_only_on_bare_turn_on` is enabled. This is CORRECT behavior - scenes should persist.

## Initial Fix Mistake

The initial fix in PR #1380 incorrectly:
1. Renamed `_mark_manual_control_if_non_bare_turn_on` to `_is_non_bare_turn_on`
2. **Removed** the `set_manual_control_attributes` call
3. Added a docstring claiming it doesn't mark as manually controlled

This broke the `adapt_only_on_bare_turn_on` feature - scenes would no longer persist because lights weren't being marked as manually controlled.

## Correct Fix

The fix requires TWO changes:

### 1. Fix the regression in `turn_on_off_event_listener.on()`

Only check for manual control when the light was ALREADY ON (not when turning on from OFF):

```python
async def on(eid: str, event: Event) -> None:
    task = self.sleep_tasks.get(eid)
    if task is not None:
        task.cancel()
    self.turn_on_event[eid] = event

    # Only check for manual control if light was already ON.
    # Turning on from OFF should never mark as manually controlled.
    # Fix for https://github.com/basnijholt/adaptive-lighting/issues/1378
    state = self.hass.states.get(eid)
    if state is not None and state.state == STATE_ON:
        try:
            switch = _switch_with_lights(self.hass, [eid], expand_light_groups=False)
            await self.update_manually_controlled_from_event(switch, eid, force=False)
        except NoSwitchFoundError:
            _LOGGER.debug("No switch found for entity_id='%s' in 'on' event listener", eid)
```

### 2. Keep `_mark_manual_control_if_non_bare_turn_on` intact

Do NOT rename or modify this function. It should continue to mark lights as manually controlled when `adapt_only_on_bare_turn_on` is enabled and attributes are present. This is the correct behavior for preserving scenes.

### 3. Apply code style suggestion

Use `self.get_manual_control_attributes(light)` instead of `self.manual_control.get(light, LightControlAttributes.NONE)` in `set_manual_control_attributes` logging.

## Expected Behavior After Fix

| Scenario | `adapt_only_on_bare_turn_on` | Result |
|----------|------------------------------|--------|
| Turn on from OFF with brightness | `False` | NOT manually controlled (fix for #1378) |
| Turn on from OFF with brightness | `True` | Manually controlled (preserves scenes) |
| Turn on from OFF without attributes | Either | NOT manually controlled |
| Change brightness while ON | Either | Manually controlled |

## Test Expectations

The test `test_manual_control` is parameterized with `adapt_only_on_bare_turn_on` being both True and False:

```python
# Turning on from OFF with brightness:
# - With adapt_only_on_bare_turn_on=True: SHOULD mark as manually controlled (to preserve scenes)
# - With adapt_only_on_bare_turn_on=False: should NOT mark (fix for issue #1378)
if adapt_only_on_bare_turn_on:
    assert manual_control[ENTITY_LIGHT_1] == LightControlAttributes.BRIGHTNESS
else:
    assert not manual_control[ENTITY_LIGHT_1]
```

## Files Changed

- `custom_components/adaptive_lighting/switch.py`:
  - Fix in `turn_on_off_event_listener.on()` - only check manual control when light was already ON
  - Keep `_mark_manual_control_if_non_bare_turn_on` intact (reverted incorrect change)
  - Use getter method in logging (code style)
- `tests/test_switch.py`: Update test expectations based on `adapt_only_on_bare_turn_on` setting

## Test Results

All 173 tests pass after the corrected fix.

## protyposis Review Comments

### Comment 1 (Code Style) - APPLIED
Suggests using `self.get_manual_control_attributes(light)` instead of `self.manual_control.get(light, LightControlAttributes.NONE)`. Applied.

### Comment 2 (Design Question) - ANSWERED
> "With #1356, shouldn't an initial turn on with brightness still adapt color (unless `adapt_only_on_bare_turn_on` is enabled)?"

Answer: Yes, that's exactly what the fix does:
- When `adapt_only_on_bare_turn_on=False`: Light is NOT marked as manually controlled, AL adapts everything
- When `adapt_only_on_bare_turn_on=True` AND attributes present: Light IS marked as manually controlled (via `_mark_manual_control_if_non_bare_turn_on` in `_respond_to_off_to_on_event`) - this preserves scenes

### Comment 3 (Reproduction Issue)
protyposis couldn't reproduce the bug. This might be because:
- The bug manifests with specific light integrations (Z2M) or light groups
- Context ID matching issues with light groups
- Timing-dependent behavior

The fix addresses the root cause regardless of reproduction difficulty.
