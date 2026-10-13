"""Plan native-group attributes at a complete service-request boundary.

Original handlers retain power and attributes that cannot safely be consolidated. A
scene supplies its complete intended states before HA's cached-state filtering;
independent service calls never acquire coverage by sharing a context or timer.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from typing import TYPE_CHECKING, Any
from weakref import WeakKeyDictionary

from homeassistant.auth.permissions.const import POLICY_CONTROL
from homeassistant.components.light import (
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_SUPPORTED_COLOR_MODES,
    ATTR_TRANSITION,
    ColorMode,
    LightEntityFeature,
    brightness_supported,
    preprocess_turn_on_alternatives,
)
from homeassistant.components.light import (
    reproduce_state as light_reproduce_state,
)
from homeassistant.components.light.const import DATA_COMPONENT, DATA_PROFILES
from homeassistant.components.light.reproduce_state import (
    COLOR_GROUP,
    COLOR_MODE_TO_ATTRIBUTE,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    CONF_PARAMS,
    ENTITY_MATCH_ALL,
    EVENT_SERVICE_REGISTERED,
    SERVICE_TOGGLE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import (
    Context,
    Event,
    ServiceCall,
    ServiceResponse,
    State,
    callback,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.util.color import color_temperature_mired_to_kelvin

from .adaptation_utils import (
    BRIGHTNESS_ATTRS,
    COLOR_ATTRS,
    LightControlAttributes,
    adaptation_command_sequence,
    has_effect_attribute,
)
from .hass_utils import (
    ServiceContinuation,
    setup_service_call_interceptor,
    target_entities,
)
from .native_group_models import (
    ActivationClaim,
    ActivationCoverage,
    AdaptiveRevision,
    AttributePolicy,
    DispatchDecision,
    LightRequests,
    NativeBatch,
    NativeGroup,
    NativeIntent,
    NativePlan,
    Parameters,
)

if TYPE_CHECKING:
    from collections.abc import (
        Awaitable,
        Callable,
        Iterable,
        Iterator,
        Mapping,
        Sequence,
    )

    from .switch import AdaptiveLightingManager, AdaptiveSwitch

# Older HA schemas add the deprecated mired alias alongside Kelvin. It must
# travel with the same colour intent, never leak into the power-only dispatch.
_COLOUR_PARAMS = COLOR_ATTRS | {"color_temp", "kelvin"}


class NativeGroupPlanner:
    """Consolidate compatible attributes while retaining individual scene intent."""

    def __init__(
        self,
        manager: AdaptiveLightingManager,
        refresh_switches: Callable[[], list[AdaptiveSwitch]],
        is_ours: Callable[[Context], bool],
    ) -> None:
        """Keep planning state scoped to the manager, including hook ownership."""
        self.manager = manager
        self.hass = manager.hass
        self.refresh_switches = refresh_switches
        self.is_ours = is_ours
        self.active: ContextVar[NativeBatch | None] = ContextVar(
            "adaptive_lighting_native_batch",
            default=None,
        )
        self.versions: dict[str, int] = {}
        self.adaptive_versions: WeakKeyDictionary[AdaptiveSwitch, dict[str, int]] = (
            WeakKeyDictionary()
        )
        self.coverage: dict[str, ActivationClaim] = {}
        self.removers: list[Callable[[], None]] = []
        self.handlers: dict[tuple[str, str], Any] = {}
        self.installing: set[tuple[str, str]] = set()
        self.disabled = False

    def setup(self) -> None:
        """Hook native HA scenes, including services registered after startup."""
        self.remove_registration_listener = self.hass.bus.async_listen(
            EVENT_SERVICE_REGISTERED,
            self._registered,
        )
        for domain, service in (
            ("scene", "apply"),
            ("scene", SERVICE_TURN_ON),
            ("light", SERVICE_TURN_OFF),
        ):
            self._install(domain, service)

    @callback
    def _registered(self, event: Event) -> None:
        self._install(event.data["domain"], event.data["service"])

    def _install(self, domain: str, service: str) -> None:
        if self.disabled or (domain, service) not in {
            ("scene", "apply"),
            ("scene", SERVICE_TURN_ON),
            ("light", SERVICE_TURN_OFF),
        }:
            return
        key = (domain, service)
        if key in self.installing:
            return
        registered = self.hass.services._services.get(domain, {}).get(service)
        if registered is None or registered.job.target is self.handlers.get(
            (domain, service),
        ):
            return
        # Older HA dispatches registration events synchronously. A wrapper's
        # own registration must not install another wrapper before this one
        # has been recorded; other services remain eligible during the call.
        self.installing.add(key)
        try:
            self.removers.append(
                setup_service_call_interceptor(
                    self.hass,
                    domain,
                    service,
                    self._before_off,
                    around_func=self.around_scene if domain == "scene" else None,
                ),
            )
            self.handlers[key] = self.hass.services._services[domain][
                service
            ].job.target
        finally:
            self.installing.remove(key)

    def disable(self) -> None:
        """Retire pending plans and restore only service handlers we still own."""
        self.disabled = True
        self.remove_registration_listener()
        for remove in reversed(self.removers):
            remove()
        self.coverage.clear()
        self.versions.clear()
        self.adaptive_versions.clear()

    def _refresh_groups(self, requested: Iterable[str] = ()) -> dict[str, NativeGroup]:
        """Refresh profile ownership explicitly before taking a group snapshot."""
        return self._select_groups(self.refresh_switches(), requested)

    def _select_groups(
        self,
        profiles: Sequence[AdaptiveSwitch],
        requested: Iterable[str],
    ) -> dict[str, NativeGroup]:
        """Resolve competing profiles independently for brightness and colour."""
        switches = [switch for switch in profiles if switch.is_on]
        memberships = {
            group: frozenset(
                member
                for member, parents in switch._group_members.items()
                if group in parents
            )
            for switch in switches
            for group in switch.lights
            if any(group in parents for parents in switch._group_members.values())
        }
        for group in requested:
            state = self.hass.states.get(group)
            members = state.attributes.get("group_entities", ()) if state else ()
            if (
                isinstance(members, (list, tuple))
                and members
                and all(
                    isinstance(member, str) and member != group for member in members
                )
            ):
                memberships[group] = frozenset(members)
        groups = {}
        for group, members in memberships.items():
            owners = {}
            for attribute in (
                LightControlAttributes.BRIGHTNESS,
                LightControlAttributes.COLOR,
            ):
                enabled = [
                    switch
                    for switch in switches
                    if (
                        switch.adapt_brightness_switch.is_on
                        if attribute == LightControlAttributes.BRIGHTNESS
                        else switch.adapt_color_switch.is_on
                    )
                ]
                per_member = [
                    {switch for switch in enabled if member in switch._tracked_lights}
                    for member in members
                ]
                shared = set.intersection(*per_member)
                if len(shared) == 1 and all(
                    len(candidates) == 1 for candidates in per_member
                ):
                    owner = next(iter(shared))
                    # Derived groups are eligible only inside a profile's known
                    # native membership, not merely a list of unrelated lights.
                    if members <= owner._group_members.keys():
                        owners[attribute] = owner
            if owners:
                groups[group] = NativeGroup(owners, members)
        return groups

    async def _before_off(self, call: ServiceCall, _data: dict) -> None:
        if call.domain == "light" and not self.is_ours(call.context):
            targets = await self._light_targets(call)
            if targets is not None:
                self.invalidate(targets)

    async def _light_targets(self, call: ServiceCall) -> set[str] | None:
        """Match HA's light targets and implicit-all permission filtering."""
        component = self.hass.data[DATA_COMPONENT]
        if call.data.get(ATTR_ENTITY_ID) == ENTITY_MATCH_ALL:
            targets = {
                entity.entity_id for entity in component.entities if entity.available
            }
            if call.context.user_id is None:
                return targets
            user = await self.hass.auth.async_get_user(call.context.user_id)
            if user is None:
                return None
            return {
                entity
                for entity in targets
                if user.is_admin
                or user.permissions.check_entity(entity, POLICY_CONTROL)
            }
        targets = target_entities(self.hass, dict(call.data), expand_group=True)
        if not await self._authorized(call.context, targets):
            return None
        return {
            target
            for target in targets
            if (entity := component.get_entity(target)) is not None and entity.available
        }

    def invalidate(self, entities: Iterable[str]) -> None:
        """A newer request or real OFF invalidates old activation coverage."""
        targets = set(entities)
        # OFF remains authoritative after a profile is disabled. Resolve the
        # device's current membership independently of enabled AL profiles.
        for entity in tuple(targets):
            state = self.hass.states.get(entity)
            members = state.attributes.get("group_entities", ()) if state else ()
            if isinstance(members, (list, tuple)):
                targets.update(
                    member
                    for member in members
                    if isinstance(member, str) and member.startswith("light.")
                )
        for entity in targets:
            self.versions[entity] = self.versions.get(entity, 0) + 1
            self.coverage.pop(entity, None)

    def invalidate_adaptive(
        self,
        switch: AdaptiveSwitch,
        entities: Iterable[str] | None = None,
    ) -> None:
        """Retire an owner's computed settings while preserving explicit intent."""
        targets = set(switch._tracked_lights if entities is None else entities)
        for entity in tuple(targets):
            state = self.hass.states.get(entity)
            members = state.attributes.get("group_entities", ()) if state else ()
            if isinstance(members, (list, tuple)):
                targets.update(member for member in members if isinstance(member, str))
        versions = self.adaptive_versions.setdefault(switch, {})
        for entity in targets:
            versions[entity] = versions.get(entity, 0) + 1

    def take_activation_claim(self, entity: str) -> ActivationClaim | None:
        """Assign an expected report to one handler without freezing its validity."""
        return self.coverage.pop(entity, None)

    def activation_superseded(
        self,
        claim: ActivationClaim | None,
    ) -> bool:
        """A newer request retires this report, independently of owner changes."""
        return claim is not None and any(
            version != self.versions.get(entity, 0)
            for entity, version in claim.request_versions
        )

    def activation_coverage(
        self,
        entity: str,
        claim: ActivationClaim | None,
        context: Context | None = None,
    ) -> ActivationCoverage:
        """Revalidate captured report coverage after lifecycle and settings changes."""
        if claim is None:
            return ActivationCoverage()
        valid = (
            not claim.execution.aborted
            and entity not in claim.execution.failed_members
            and not self.activation_superseded(claim)
            and (
                claim.required_context_id is None
                or (context is not None and context.id == claim.required_context_id)
            )
        )
        attributes = claim.attributes if valid else LightControlAttributes.NONE
        for revision in claim.adaptive_revisions:
            if revision.version != self.adaptive_versions.get(revision.owner, {}).get(
                revision.member,
                0,
            ):
                attributes &= ~revision.attributes
        return ActivationCoverage(
            LightControlAttributes.COLOR in attributes,
            LightControlAttributes.BRIGHTNESS in attributes,
            bool(attributes) and claim.aggregate_only,
        )

    def claimed(self, entity: str) -> bool:
        """Keep the original interceptor from adapting a planned target twice."""
        batch = self.active.get()
        return bool(
            batch and not batch.execution.closed and entity in batch.plan.requests,
        )

    @staticmethod
    def _scene_params(state: State, transition: float | None) -> dict[str, Any] | None:
        attrs = state.attributes
        params = {
            key: attrs[key]
            for key in ("brightness", "effect")
            if attrs.get(key) is not None
        }
        mode = attrs.get("color_mode", ColorMode.UNKNOWN)
        if mode != ColorMode.UNKNOWN:
            pair = COLOR_MODE_TO_ATTRIBUTE.get(mode)
            if pair:
                value = attrs.get(pair.state_attr)
                if value is None:
                    if (
                        mode == ColorMode.COLOR_TEMP
                        and "color_temp" in COLOR_GROUP
                        and attrs.get("color_temp")
                    ):
                        value = color_temperature_mired_to_kelvin(attrs["color_temp"])
                    else:
                        # HA rejects this malformed desired state as well.
                        return None
                params[pair.parameter] = value
        else:
            for entry in COLOR_GROUP:
                # HA 2025 uses attribute strings; newer releases pair state
                # attributes with service parameters.
                key, param = (entry, entry) if isinstance(entry, str) else entry
                if attrs.get(key) is not None:
                    params[param] = attrs[key]
                    break
        if transition is not None:
            params[ATTR_TRANSITION] = transition
        return params

    def _normalized_params(self, params: Parameters) -> dict[str, Any]:
        params = dict(params)
        if ATTR_COLOR_TEMP_KELVIN in params:
            # Legacy HA also supplies a rounded mired alias. Reprocessing it
            # must not overwrite the exact Kelvin value or change scene intent.
            params.pop("color_temp", None)
            params.pop("kelvin", None)
        preprocess_turn_on_alternatives(self.hass, params)
        if ATTR_COLOR_TEMP_KELVIN not in params and params.get("color_temp"):
            params[ATTR_COLOR_TEMP_KELVIN] = color_temperature_mired_to_kelvin(
                params["color_temp"],
            )
        if ATTR_COLOR_TEMP_KELVIN in params:
            params.pop("color_temp", None)
            params.pop("kelvin", None)
        return {
            key: tuple(value) if isinstance(value, (list, tuple)) else value
            for key, value in params.items()
        }

    def _effective_params(self, entity: str, params: Parameters) -> dict[str, Any]:
        """Resolve HA light-profile defaults before comparing colour intents."""
        params = self._normalized_params(params)
        light = self.hass.data[DATA_COMPONENT].get_entity(entity)
        is_on = (
            light.is_on
            if light is not None
            else self.hass.states.is_state(entity, STATE_ON)
        )
        if not params or not is_on or ATTR_TRANSITION not in params:
            self.hass.data[DATA_PROFILES].apply_default(entity, is_on, params)
        return params

    async def _authorized(self, context: Context, entities: Iterable[str]) -> bool:
        """Only replace dispatch when the original targets are controllable."""
        if context.user_id is None:
            return True
        user = await self.hass.auth.async_get_user(context.user_id)
        return user is not None and (
            user.is_admin
            or all(
                user.permissions.check_entity(entity, POLICY_CONTROL)
                for entity in entities
            )
        )

    def _scene_requests(self, call: ServiceCall) -> dict[str, dict[str, Any]]:
        if call.service == "apply":
            states = list(call.data["entities"].values())
        else:
            platform = self.hass.data.get("homeassistant_scene")
            if platform is None:
                return {}
            states = []
            for target in sorted(target_entities(self.hass, dict(call.data))):
                scene = platform.entities.get(target)
                config = getattr(scene, "scene_config", None)
                if config is None:
                    # Opaque integration scenes cannot provide full intent.
                    return {}
                states.extend(config.states.values())
        requests = {}
        for state in states:
            if not isinstance(state, State) or state.domain != "light":
                continue
            if state.entity_id in requests:
                # Multiple scene targets can race; do not invent an ordering.
                return {}
            params = self._scene_params(state, call.data.get(ATTR_TRANSITION))
            if params is None:
                continue
            requests[state.entity_id] = {
                "state": state.state,
                **self._normalized_params(params),
            }
        return requests

    async def around_scene(
        self,
        call: ServiceCall,
        invoke: ServiceContinuation,
    ) -> ServiceResponse:
        """Capture desired states before HA filters or fans them out."""
        # Every scene invocation owns its light reproduction, including opaque
        # scenes that cannot provide a plan before their handler runs.
        with self._suspend_batch():
            if self.disabled or self.is_ours(call.context):
                return await invoke()
            if call.service == SERVICE_TURN_ON and not await self._authorized(
                call.context,
                target_entities(self.hass, dict(call.data)),
            ):
                return await invoke()
            requests = self._scene_requests(call)
            batch = await self._prepare(call.context, requests)
            if batch is None:
                return await invoke()
            return await self._run(batch, invoke)

    async def around_light(
        self,
        call: ServiceCall,
        invoke: ServiceContinuation,
    ) -> ServiceResponse:
        """Only HA's actual light reproduction task may join a scene batch."""
        if self.disabled or self.is_ours(call.context):
            with self._suspend_batch():
                return await invoke()
        targets = await self._light_targets(call)
        if targets is None:
            with self._suspend_batch():
                return await invoke()
        params = self._normalized_params(call.data[CONF_PARAMS])
        batch = self.active.get()
        if (
            batch
            and not batch.execution.closed
            and self._is_scene_reproduction()
            and call.context.id == batch.plan.context.id
            and all(
                target in batch.plan.requests
                and not (
                    batch.plan.groups[target].members
                    if target in batch.plan.groups
                    else {target}
                ).intersection(batch.execution.accepted_members)
                and batch.plan.requests[target] == {"state": STATE_ON, **params}
                for target in targets
            )
        ):
            return await self._dispatch_light(batch, call, invoke, targets)
        # Events and nested integration calls can inherit a scene's ContextVar
        # and even reuse its HA Context. Their preprocessing and fallback must
        # not see the older operation's claimed targets.
        with self._suspend_batch():
            requests = {
                target: {
                    "state": (
                        STATE_OFF
                        if call.service == SERVICE_TOGGLE
                        and self.hass.states.is_state(target, STATE_ON)
                        else STATE_ON
                    ),
                    **params,
                }
                for target in targets
            }
            batch = await self._prepare(call.context, requests)
            if batch is None:
                return await invoke()

            return await self._run_light(batch, call, invoke, targets)

    def _light_partitions(
        self,
        batch: NativeBatch,
        targets: set[str],
    ) -> list[tuple[NativeBatch, set[str]]]:
        """Keep shared native broadcasts/reports together; separate unrelated targets.

        Even a partially covered ancestor connects its requested descendants:
        its aggregate activation claim must belong to one execution, never be
        overwritten by two independently completing batches. Scenes retain their
        original complete-request boundary and do not use this partitioning.
        """
        plan = batch.plan
        target_members = {}
        for target in targets:
            if candidate := plan.groups.get(target):
                target_members[target] = candidate.members
                continue
            # An unowned/unsupported native target still broadcasts to its
            # advertised members. This establishes connectivity only; it never
            # grants adaptation eligibility or extends command/claim coverage.
            state = self.hass.states.get(target)
            members = state.attributes.get("group_entities", ()) if state else ()
            target_members[target] = (
                frozenset(members)
                if isinstance(members, (list, tuple))
                and members
                and all(
                    isinstance(member, str) and member != target for member in members
                )
                else {target}
            )
        components = [{target} for target in sorted(targets)]
        for group in plan.groups.values():
            related = [
                component
                for component in components
                if any(target_members[target] & group.members for target in component)
            ]
            if len(related) > 1:
                components = [c for c in components if c not in related]
                components.append(set().union(*related))
        if len(components) == 1:
            return [(batch, targets)]
        partitions = []
        for component in sorted(components, key=min):
            members = set().union(*(target_members[target] for target in component))
            partitions.append(
                (
                    NativeBatch(
                        NativePlan(
                            plan.context,
                            {
                                target: plan.requests[target]
                                for target in component
                                if target in plan.requests
                            },
                            {
                                name: group
                                for name, group in plan.groups.items()
                                if group.members & members
                            },
                            {
                                member: intent
                                for member, intent in plan.intents.items()
                                if member in members
                            },
                        ),
                    ),
                    component,
                ),
            )
        return partitions

    async def _run_light(
        self,
        batch: NativeBatch,
        call: ServiceCall,
        invoke: ServiceContinuation,
        targets: set[str],
    ) -> ServiceResponse:
        """A slow original handler cannot hold an unrelated group's adaptation."""

        async def run(partition: NativeBatch, selected: set[str]) -> ServiceResponse:
            async def dispatch() -> None:
                await self._dispatch_light(partition, call, invoke, selected)

            return await self._run(partition, dispatch)

        partitions = self._light_partitions(batch, targets)
        if len(partitions) == 1:
            return await run(*partitions[0])
        results = await asyncio.gather(
            *(run(partition, selected) for partition, selected in partitions),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result
        return None

    @staticmethod
    def _is_scene_reproduction() -> bool:
        """Recognize HA's direct light reproduction worker, not inherited events.

        This private HA function is an optimization boundary only. If HA changes
        its worker or task shape, independent light dispatch preserves behaviour
        without grouping the scene. Neither shared Context nor timing is proof
        that another service call belongs to the scene.
        """
        task = asyncio.current_task()
        worker = getattr(light_reproduce_state, "_async_reproduce_state", None)
        code = getattr(worker, "__code__", None)
        return bool(
            code is not None
            and task is not None
            and getattr(task.get_coro(), "cr_code", None) is code,
        )

    @contextmanager
    def _suspend_batch(self) -> Iterator[None]:
        """Run an independent request without inheriting an older scene plan."""
        token = self.active.set(None)
        try:
            yield
        finally:
            self.active.reset(token)

    async def _prepare(
        self,
        context: Context,
        requests: LightRequests,
    ) -> NativeBatch | None:
        if not await self._authorized(context, requests):
            return None
        # New intent supersedes pending work even after its profile or colour
        # switch is disabled, or the target is removed from the native group.
        self.invalidate(requests)
        groups = self._refresh_groups(requests)
        relevant = set(groups)
        relevant.update(member for group in groups.values() for member in group.members)
        requests = {key: value for key, value in requests.items() if key in relevant}
        # HA resolves relative brightness using the live entity before applying
        # defaults. Leave those commands in that handler rather than guessing.
        if not requests or any(
            {"brightness_step", "brightness_step_pct"}.intersection(request)
            for request in requests.values()
        ):
            return None
        authorized_targets = set(requests)
        authorized_targets.update(
            member
            for target in requests
            if target in groups
            for member in groups[target].members
        )
        if not await self._authorized(context, authorized_targets):
            # Preserve HA's own permission errors and target-selection rules.
            return None
        intents: dict[str, NativeIntent] = {}
        for target, request in requests.items():
            if (
                request["state"] != STATE_ON
                or has_effect_attribute(request)
                or "white" in request
            ):
                continue
            members = groups[target].members if target in groups else {target}
            owners = {
                attribute: owner
                for group in groups.values()
                if members <= group.members
                for attribute, owner in group.owners.items()
            }
            for member in members:
                effective_request = {
                    **request,
                    **self._effective_params(
                        target,
                        {
                            key: value
                            for key, value in request.items()
                            if key != "state"
                        },
                    ),
                }
                intent = await self._member_intent(
                    member,
                    effective_request,
                    owners,
                    context,
                    target,
                )
                if intent is None:
                    continue
                if member in intents:
                    # Overlapping group/member requests have no single colour intent.
                    return None
                intents[member] = intent
        on_members = {
            member
            for target, request in requests.items()
            if request["state"] == STATE_ON
            and request.get("brightness") != 0
            and request.get("brightness_pct") != 0
            for member in (groups[target].members if target in groups else {target})
        }
        if not intents or (
            not any(intent.explicit for intent in intents.values())
            and not any(
                candidate.members <= on_members for candidate in groups.values()
            )
        ):
            # An isolated bare activation retains the established reactive path,
            # including its combined axes and cancellation during adapt_delay.
            return None
        await self._plan_group_brightness(context, groups, intents)
        intents = {
            member: intent for member, intent in intents.items() if intent.attributes
        }
        return (
            NativeBatch(NativePlan(context, requests, groups, intents))
            if intents
            else None
        )

    def _cover_activations(self, batch: NativeBatch) -> None:
        """Cover only reports of power changes this request actually intends."""
        requests, groups = batch.plan.requests, batch.plan.groups
        expected_activations = {
            member
            for target, request in requests.items()
            if request["state"] == STATE_ON
            and request.get("brightness") != 0
            and (
                target not in groups
                or BRIGHTNESS_ATTRS.intersection(request)
                or not _COLOUR_PARAMS.intersection(request)
            )
            for member in (groups[target].members if target in groups else {target})
            if self.hass.states.is_state(member, STATE_OFF)
        }
        for member in batch.plan.intents.keys() & expected_activations:
            self.coverage[member] = self._activation_claim(batch, member)
        for group, candidate in groups.items():
            members = candidate.members
            if (
                members & batch.plan.intents.keys() & expected_activations
                or self._colour_only(requests.get(group, {}))
            ):
                self.coverage[group] = self._activation_claim(batch, group)

    def _activation_claim(self, batch: NativeBatch, entity: str) -> ActivationClaim:
        """Snapshot report semantics while the plan is available, before dispatch."""
        plan = batch.plan
        group = plan.groups.get(entity)
        intents = (
            [(entity, plan.intents[entity])]
            if entity in plan.intents
            else [
                (member, plan.intents[member])
                for member in (group.members if group else ())
                if member in plan.intents
            ]
        )
        colour_only_group = group is not None and self._colour_only(
            plan.requests.get(entity, {}),
        )
        brightness_supplied = (
            bool(BRIGHTNESS_ATTRS.intersection(plan.requests.get(entity, {})))
            or bool(plan.intents.get(entity) and plan.intents[entity].brightness)
            or any(
                entity in candidate.members
                and BRIGHTNESS_ATTRS.intersection(plan.requests.get(target, {}))
                for target, candidate in plan.groups.items()
            )
            or any(
                entity == target
                and candidate.members <= plan.intents.keys()
                and all(plan.intents[member].brightness for member in candidate.members)
                for target, candidate in plan.groups.items()
            )
        )
        return ActivationClaim(
            execution=batch.execution,
            request_versions=tuple(
                (target, self.versions.get(target, 0))
                for target in sorted(
                    {entity} | (set(group.members) if group else set()),
                )
            ),
            adaptive_revisions=tuple(
                AdaptiveRevision(policy.owner, member, policy.version, attribute)
                for member, intent in intents
                for attribute, policy in intent.policies.items()
                if attribute not in intent.explicit
            ),
            attributes=(
                (
                    LightControlAttributes.BRIGHTNESS
                    if brightness_supplied
                    else LightControlAttributes.NONE
                )
                | (
                    LightControlAttributes.COLOR
                    if intents and all(intent.colour for _, intent in intents)
                    else LightControlAttributes.NONE
                )
            ),
            aggregate_only=(group is not None and entity not in plan.requests)
            or colour_only_group,
            required_context_id=plan.context.id if colour_only_group else None,
        )

    @staticmethod
    def _colour_only(request: Parameters) -> bool:
        """A native colour update does not promise to power its OFF members."""
        return bool(
            _COLOUR_PARAMS.intersection(request),
        ) and not BRIGHTNESS_ATTRS.intersection(request)

    async def _plan_group_brightness(
        self,
        context: Context,
        groups: Mapping[str, NativeGroup],
        intents: dict[str, NativeIntent],
    ) -> None:
        """Defer brightness only when a complete compatible group can carry it.

        Other explicit brightness stays in HA's original payload. Computed
        individual brightness retains the established activation response.
        """
        covered = set()
        for group, candidate in groups.items():
            members = candidate.members
            if not members <= intents.keys():
                continue
            intent = intents[next(iter(members))].select(
                LightControlAttributes.BRIGHTNESS,
            )
            owner = candidate.owners.get(LightControlAttributes.BRIGHTNESS)
            if (
                not intent.brightness
                or owner is None
                or not self._group_permitted(
                    owner,
                    group,
                    members,
                    LightControlAttributes.BRIGHTNESS,
                )
            ):
                continue
            if not await self._authorized(context, [group]):
                continue
            if (
                not self._compatible(group, intent.brightness)
                or self._effective_params(group, intent.brightness) != intent.brightness
            ):
                continue
            if all(
                intents[member].brightness == intent.brightness
                and intents[member].policies[LightControlAttributes.BRIGHTNESS].owner
                is owner
                and self._ready_delay(
                    intents[member].select(LightControlAttributes.BRIGHTNESS),
                )
                == self._ready_delay(intent)
                and self._compatible(member, intent.brightness)
                for member in members
            ):
                covered.update(members)
        for member in intents.keys() - covered:
            intents[member] = intents[member].select(LightControlAttributes.COLOR)

    async def _member_intent(
        self,
        member: str,
        request: Parameters,
        owners: Mapping[LightControlAttributes, AdaptiveSwitch],
        context: Context,
        source: str,
    ) -> NativeIntent | None:
        params = self._normalized_params(
            {key: value for key, value in request.items() if key != "state"},
        )
        if params.get("brightness") == 0:
            return None
        explicit = LightControlAttributes.NONE
        payloads = {}
        policies = {}
        for attribute, keys in (
            (LightControlAttributes.COLOR, COLOR_ATTRS),
            (LightControlAttributes.BRIGHTNESS, BRIGHTNESS_ATTRS),
        ):
            switch = owners.get(attribute)
            if switch is None or not self._permitted(switch, member, attribute):
                continue
            payload = {key: value for key, value in params.items() if key in keys}
            if payload:
                explicit |= attribute
                if ATTR_TRANSITION in params:
                    payload[ATTR_TRANSITION] = params[ATTR_TRANSITION]
            else:
                if not self._can_compute_attribute(
                    switch,
                    member,
                    source,
                    attribute,
                    params,
                ):
                    continue
                if switch._take_over_control and switch._adapt_only_on_bare_turn_on:
                    self.manager._mark_manual_control_if_non_bare_turn_on(
                        member,
                        params,
                    )
                if not self._permitted(
                    switch,
                    member,
                    attribute,
                ) or attribute not in self.manager.get_adaption_control_attributes(
                    switch,
                    source,
                ):
                    continue
                data = await switch.prepare_adaptation_data(
                    member,
                    params.get(ATTR_TRANSITION, switch.initial_transition),
                    adapt_brightness=attribute == LightControlAttributes.BRIGHTNESS,
                    adapt_color=attribute == LightControlAttributes.COLOR,
                    force=True,
                    context=context,
                )
                if data is None:
                    continue
                payload = await data.next_service_call_data()
                if not payload:
                    continue
                payload.pop(ATTR_ENTITY_ID, None)
            payloads[attribute] = payload
            policies[attribute] = AttributePolicy(
                switch,
                self.adaptive_versions.get(switch, {}).get(member, 0),
            )
        if not payloads:
            return None
        return NativeIntent(
            payloads.get(LightControlAttributes.COLOR, {}),
            explicit,
            self.versions.get(member, 0),
            source,
            policies,
            payloads.get(LightControlAttributes.BRIGHTNESS, {}),
        )

    def _can_compute_attribute(
        self,
        switch: AdaptiveSwitch,
        member: str,
        source: str,
        attribute: LightControlAttributes,
        params: Parameters,
    ) -> bool:
        """Missing scene brightness does not change already-ON members implicitly."""
        member_on = self.hass.states.is_state(member, STATE_ON)
        if switch._only_once and member_on:
            return False
        if attribute != LightControlAttributes.BRIGHTNESS:
            return True
        state = self.hass.states.get(source)
        activating_group = state is not None and any(
            self.hass.states.is_state(target, STATE_OFF)
            for target in state.attributes.get("group_entities", ())
        )
        colour_only_group = bool(
            state
            and state.attributes.get("group_entities")
            and COLOR_ATTRS.intersection(params),
        )
        return not colour_only_group and (not member_on or activating_group)

    def _permitted(
        self,
        switch: AdaptiveSwitch,
        member: str,
        attributes: LightControlAttributes,
    ) -> bool:
        state = self.hass.states.get(member)
        return (
            not self.disabled
            and not switch._removed
            and switch.is_on
            and member in switch._tracked_lights
            and state is not None
            and state.state in (STATE_ON, STATE_OFF)
            and attributes
            in self.manager.get_adaption_control_attributes(switch, member)
        )

    def _group_permitted(
        self,
        switch: AdaptiveSwitch,
        group: str,
        members: frozenset[str],
        attributes: LightControlAttributes,
    ) -> bool:
        """Apply both group and member guards to configured or derived groups."""
        return all(
            self._permitted(switch, member, attributes) for member in members
        ) and attributes in self.manager.get_adaption_control_attributes(
            switch,
            group,
        )

    async def _dispatch_light(
        self,
        batch: NativeBatch,
        call: ServiceCall,
        invoke: ServiceContinuation,
        targets: set[str],
    ) -> None:
        """Keep scene error recovery behind every observed child dispatch."""
        completion = self.hass.loop.create_future()
        batch.execution.children.add(completion)
        try:
            await self._dispatch_light_targets(batch, call, invoke, targets)
        finally:
            batch.execution.children.discard(completion)
            if not completion.done():
                completion.set_result(None)

    async def _dispatch_light_targets(
        self,
        batch: NativeBatch,
        call: ServiceCall,
        invoke: ServiceContinuation,
        targets: set[str],
    ) -> None:
        # Keep HA's independent-target concurrency, including unmanaged targets.
        # Only covered members may defer attributes; each other original payload is
        # dispatched intact and is never retried after an error.
        covered = set(batch.plan.intents)
        covered.update(
            group
            for group, candidate in batch.plan.groups.items()
            if candidate.members <= covered
        )
        params = dict(call.data[CONF_PARAMS])
        ordered_targets = sorted(targets)

        async def dispatch(target: str) -> None:
            members = (
                batch.plan.groups[target].members
                if target in batch.plan.groups
                else {target}
            )
            if any(
                batch.plan.intents[member].version != self.versions.get(member, 0)
                for member in members & batch.plan.intents.keys()
            ):
                return
            decision = self._original_dispatch_decision(
                batch.plan,
                target,
                params,
                covered,
            )
            batch.execution.forward(members, decision.forwarded)
            if decision.params is None:
                batch.execution.accept(members & batch.plan.intents.keys())
                return
            await invoke(
                ServiceCall(
                    self.hass,
                    call.domain,
                    call.service,
                    {
                        **{
                            key: value
                            for key, value in call.data.items()
                            if key not in cv.ENTITY_SERVICE_FIELDS
                        },
                        ATTR_ENTITY_ID: [target],
                        CONF_PARAMS: dict(decision.params),
                    },
                    context=call.context,
                    return_response=call.return_response,
                ),
            )
            batch.execution.accept(members & batch.plan.intents.keys())

        results = await asyncio.gather(
            *(dispatch(target) for target in ordered_targets),
            return_exceptions=True,
        )
        for target, result in zip(ordered_targets, results, strict=True):
            if isinstance(result, BaseException):
                members = (
                    batch.plan.groups[target].members
                    if target in batch.plan.groups
                    else {target}
                )
                self._dispatch_failed(batch, members, result)

    def _dispatch_failed(
        self,
        batch: NativeBatch,
        members: Iterable[str],
        error: BaseException,
    ) -> None:
        """Keep independent targets eligible without retrying failed commands."""
        batch.execution.errors.append(error)
        self._retire_members(batch, members)

    def _retire_members(self, batch: NativeBatch, members: Iterable[str]) -> None:
        """Discard pending attributes and activation claims only for unsuccessful members."""
        members = set(members)
        batch.execution.retire(members)
        groups = {
            group
            for group, candidate in batch.plan.groups.items()
            if candidate.members.intersection(members)
        }
        for entity in (*members, *groups):
            claim = self.coverage.get(entity)
            if claim is not None and claim.execution is batch.execution:
                self.coverage.pop(entity)

    def _original_dispatch_decision(
        self,
        plan: NativePlan,
        target: str,
        params: Parameters,
        covered: set[str],
    ) -> DispatchDecision:
        """Defer only planned attributes, retaining native commands and HA defaults."""
        effective = self._effective_params(target, params)
        supplied = (
            LightControlAttributes.COLOR
            if _COLOUR_PARAMS.intersection(effective)
            else LightControlAttributes.NONE
        ) | (
            LightControlAttributes.BRIGHTNESS
            if BRIGHTNESS_ATTRS.intersection(effective)
            else LightControlAttributes.NONE
        )
        if target not in covered or target in plan.groups:
            return DispatchDecision(params, supplied)
        intent = plan.intents[target]
        deferred = intent.attributes & supplied
        state = self.hass.states.get(target)
        modes = state.attributes.get(ATTR_SUPPORTED_COLOR_MODES, ()) if state else ()
        if (
            ATTR_COLOR_TEMP_KELVIN in effective
            and "brightness" in effective
            and ColorMode.COLOR_TEMP not in modes
            and ColorMode.RGBWW in modes
        ):
            return DispatchDecision(params, supplied)
        keys = set()
        if LightControlAttributes.COLOR in deferred:
            keys.update(_COLOUR_PARAMS)
        if LightControlAttributes.BRIGHTNESS in deferred:
            keys.update(BRIGHTNESS_ATTRS)
        remaining = {key: value for key, value in effective.items() if key not in keys}
        if not deferred or self._effective_params(target, remaining) != remaining:
            return DispatchDecision(params, supplied)
        for attribute in (
            LightControlAttributes.BRIGHTNESS,
            LightControlAttributes.COLOR,
        ):
            selected = intent.select(attribute)
            if (
                attribute in deferred
                and self._effective_params(target, selected.parameters)
                != selected.parameters
            ):
                return DispatchDecision(params, supplied)
        # Deferred brightness supplies power itself, including for OFF members.
        if set(remaining) <= {ATTR_TRANSITION} and (
            LightControlAttributes.BRIGHTNESS in deferred
            or self.hass.states.is_state(target, STATE_ON)
        ):
            return DispatchDecision(None, supplied & ~deferred)
        return DispatchDecision(remaining, supplied & ~deferred)

    async def _run(
        self,
        batch: NativeBatch,
        invoke: Callable[[], Awaitable[ServiceResponse]],
    ) -> ServiceResponse:
        self._cover_activations(batch)
        token = self.active.set(batch)
        invocation_error = None
        try:
            try:
                result = await invoke()
            except Exception as error:
                # HA scene reproduction may raise for an unrelated entity while
                # healthy light handlers are still running. Settle those accepted
                # commands before flushing their deferred attributes; never retry a
                # failed or unobserved target. Cancellation bypasses this recovery.
                invocation_error = error
                while batch.execution.children:
                    await asyncio.gather(*tuple(batch.execution.children))
                if not batch.execution.accepted_members:
                    raise
                self._retire_members(
                    batch,
                    batch.plan.intents.keys() - batch.execution.accepted_members,
                )
            await self._flush(batch)
        except BaseException:
            batch.execution.abort()
            raise
        else:
            if invocation_error is not None:
                raise invocation_error
            if batch.execution.errors:
                raise batch.execution.errors[0]
            return result
        finally:
            batch.execution.close()
            self.active.reset(token)

    def _compatible(self, entity: str, parameters: Parameters) -> bool:
        state = self.hass.states.get(entity)
        if state is None or state.state not in (STATE_ON, STATE_OFF):
            return False
        modes = state.attributes.get(ATTR_SUPPORTED_COLOR_MODES, [])
        for mode, pair in COLOR_MODE_TO_ATTRIBUTE.items():
            if pair.parameter in parameters and mode not in modes:
                return False
        if "brightness" in parameters and not brightness_supported(set(modes)):
            return False
        kelvin = parameters.get(ATTR_COLOR_TEMP_KELVIN)
        if kelvin is not None and not (
            state.attributes.get("min_color_temp_kelvin", kelvin)
            <= kelvin
            <= state.attributes.get("max_color_temp_kelvin", kelvin)
        ):
            return False
        return not parameters.get(ATTR_TRANSITION) or bool(
            state.attributes.get(ATTR_SUPPORTED_FEATURES, 0)
            & LightEntityFeature.TRANSITION,
        )

    async def _flush(self, batch: NativeBatch) -> None:
        await self._dispatch_pending(batch, batch.plan.intents, initial_delay=True)

    def _pending_intents(
        self,
        batch: NativeBatch,
        intents: Mapping[str, NativeIntent],
    ) -> dict[str, NativeIntent]:
        """Recheck request identity and each attribute's independent ownership."""
        self._refresh_groups(batch.plan.groups)
        pending = {}
        for member, intent in intents.items():
            if (
                intent.version != self.versions.get(member, 0)
                or member in batch.execution.failed_members
            ):
                continue
            attributes = intent.attributes & ~batch.execution.forwarded.get(
                member,
                LightControlAttributes.NONE,
            )
            for attribute in (
                LightControlAttributes.BRIGHTNESS,
                LightControlAttributes.COLOR,
            ):
                if (
                    attribute in attributes
                    and attribute not in intent.explicit
                    and not self._intent_permitted(member, intent, attribute)
                ):
                    attributes &= ~attribute
            if attributes:
                pending[member] = intent.select(attributes)
        return pending

    @staticmethod
    def _ready_delay(intent: NativeIntent) -> float:
        """Only computed attributes wait for adaptive delay."""
        return max(
            (
                policy.owner._adapt_delay
                for attribute, policy in intent.policies.items()
                if attribute not in intent.explicit
            ),
            default=0,
        )

    @staticmethod
    def _combinable(intent: NativeIntent) -> bool:
        """A combined command must have one transition and one timing policy."""
        return not (intent.colour and intent.brightness) or (
            intent.brightness_wait is None
            and len({policy.owner for policy in intent.policies.values()}) == 1
            and intent.colour.get(ATTR_TRANSITION)
            == intent.brightness.get(ATTR_TRANSITION)
            and intent.explicit in (LightControlAttributes.NONE, intent.attributes)
        )

    @staticmethod
    def _split_intent(intent: NativeIntent) -> NativeIntent:
        """Retain the configured sequence even when its attributes use different targets."""
        if (
            intent.attributes != LightControlAttributes.ALL
            or intent.explicit
            or not NativeGroupPlanner._combinable(intent)
            or not intent.switch._separate_turn_on_commands
        ):
            return intent
        commands, wait = adaptation_command_sequence(
            dict(intent.parameters),
            intent.colour.get(ATTR_TRANSITION),
            intent.switch._send_split_delay / 1000.0,
            split=True,
        )
        return replace(
            intent,
            brightness=commands[0],
            colour=commands[1],
            brightness_wait=wait,
        )

    async def _reserve_dispatches(
        self,
        batch: NativeBatch,
        intents: Mapping[str, NativeIntent],
    ) -> list[tuple[str, dict[str, NativeIntent]]]:
        """Reserve shared attributes once, retaining each member's other attributes."""
        pending = self._pending_intents(batch, intents)
        dispatches = []
        groups = sorted(
            batch.plan.groups.items(),
            key=lambda item: (-len(item[1].members), item[0]),
        )
        for attributes in (
            LightControlAttributes.ALL,
            LightControlAttributes.BRIGHTNESS,
            LightControlAttributes.COLOR,
        ):
            if attributes == LightControlAttributes.BRIGHTNESS:
                pending = {
                    member: self._split_intent(intent)
                    for member, intent in pending.items()
                }
            for group, candidate in groups:
                selected = {
                    member: intent.select(attributes)
                    for member, intent in pending.items()
                    if attributes in intent.attributes
                }
                if await self._can_send_group(batch, selected, group, candidate):
                    dispatches.append(
                        (
                            group,
                            {member: selected[member] for member in candidate.members},
                        ),
                    )
                    for member in candidate.members:
                        pending[member] = pending[member].select(
                            pending[member].attributes & ~attributes,
                        )
        for member, intent in pending.items():
            if not intent.attributes:
                continue
            if self._combinable(intent):
                dispatches.append((member, {member: intent}))
            else:
                dispatches.extend(
                    (member, {member: intent.select(attribute)})
                    for attribute in (
                        LightControlAttributes.BRIGHTNESS,
                        LightControlAttributes.COLOR,
                    )
                    if attribute in intent.attributes
                )
        # Explicit attributes are due immediately. A computed overlapping
        # attribute must not delay them; equal-time phases retain brightness first.
        dispatches.sort(
            key=lambda item: self._ready_delay(next(iter(item[1].values()))),
        )
        return dispatches

    async def _dispatch_pending(
        self,
        batch: NativeBatch,
        intents: Mapping[str, NativeIntent],
        *,
        initial_delay: bool,
    ) -> None:
        """Sequence overlapping attributes while unrelated groups proceed concurrently."""
        dispatches = await self._reserve_dispatches(batch, intents)
        predecessors = {}
        tasks = []

        async def execute(target, members, dependencies, adaptation_delay):
            if dependencies:
                await asyncio.gather(*(task for task, _ in dependencies))
            results = await asyncio.gather(
                self._execute_dispatch(batch, target, members, adaptation_delay),
                return_exceptions=True,
            )
            if isinstance(results[0], BaseException):
                self._dispatch_failed(batch, members, results[0])

        for target, members in dispatches:
            dependencies = {predecessors[m] for m in members if m in predecessors}
            already_waited = min(
                (predecessors[m][1] if m in predecessors else 0 for m in members),
                default=0,
            )
            intent = next(iter(members.values()))
            required_delay = self._ready_delay(intent)
            adaptation_delay = (
                max(0, required_delay - already_waited) if initial_delay else 0
            )
            task = self.hass.async_create_task(
                execute(target, members, dependencies, adaptation_delay),
            )
            tasks.append(task)
            waited = max(already_waited, required_delay)
            predecessors.update(dict.fromkeys(members, (task, waited)))
        await asyncio.gather(*tasks)

    async def _execute_dispatch(
        self,
        batch: NativeBatch,
        target: str,
        intents: Mapping[str, NativeIntent],
        adaptation_delay: float,
    ) -> None:
        """Execute one sequence; replan only its reserved members after each wait."""
        intent = next(iter(intents.values()))
        delay = (
            intent.brightness_wait
            if intent.brightness_wait is not None
            else adaptation_delay
        )
        if delay:
            await asyncio.sleep(delay)
        pending = self._pending_intents(
            batch,
            {
                member: replace(value, brightness_wait=None)
                for member, value in intents.items()
            },
        )
        if not pending:
            return
        candidate = batch.plan.groups.get(target)
        if candidate is not None and not await self._can_send_group(
            batch,
            pending,
            target,
            candidate,
        ):
            # Membership, ownership or permissions may have changed while waiting.
            # Reuse the same reservation policy for safe subgroups/member fallbacks.
            await self._dispatch_pending(batch, pending, initial_delay=False)
            return
        intent = next(iter(pending.values()))
        members = candidate.members if candidate is not None else ()
        if (
            intent.brightness
            and intent.colour
            and not intent.explicit
            and intent.switch._separate_turn_on_commands
        ):
            commands, split_wait = adaptation_command_sequence(
                {**intent.brightness, **intent.colour},
                intent.colour.get(ATTR_TRANSITION),
                intent.switch._send_split_delay / 1000.0,
                split=True,
            )
            if len(commands) > 1:
                await self._send(
                    target,
                    replace(
                        intent.select(LightControlAttributes.BRIGHTNESS),
                        brightness=commands[0],
                    ),
                    batch.plan.context,
                    members,
                )
                await asyncio.sleep(split_wait)
            # Brightness is never repeated after an accepted first phase. The
            # shared policy also preserves duration if that phase was suppressed.
            colours = {
                member: replace(
                    member_intent.select(LightControlAttributes.COLOR),
                    colour=commands[-1],
                )
                for member, member_intent in pending.items()
            }
            await self._dispatch_pending(batch, colours, initial_delay=False)
            return
        await self._send(target, intent, batch.plan.context, members)

    async def _can_send_group(
        self,
        batch: NativeBatch,
        pending: Mapping[str, NativeIntent],
        group: str,
        candidate: NativeGroup,
    ) -> bool:
        """Revalidate the complete broadcast before dispatch and after split delays."""
        members = candidate.members
        current_groups = self._refresh_groups(batch.plan.groups)
        state = self.hass.states.get(group)
        current = current_groups.get(group)
        if (
            current is None
            or current.members != members
            or not members <= pending.keys()
            or state is None
        ):
            return False
        intent = pending[next(iter(members))]
        if any(
            current.owners.get(attribute) is not candidate.owners.get(attribute)
            for attribute in intent.policies
        ):
            return False
        return (
            set(state.attributes.get("group_entities", [])) == members
            and all(
                attribute in candidate.owners
                and self._group_permitted(
                    candidate.owners[attribute],
                    group,
                    members,
                    attribute,
                )
                for attribute in intent.policies
            )
            and await self._authorized(batch.plan.context, [group])
            and self._combinable(intent)
            and self._compatible(group, intent.parameters)
            and self._effective_params(group, intent.parameters) == intent.parameters
            and all(
                pending[member].version == self.versions.get(member, 0)
                and pending[member].explicit == intent.explicit
                and pending[member].brightness_wait == intent.brightness_wait
                and pending[member].colour == intent.colour
                and self._ready_delay(pending[member]) == self._ready_delay(intent)
                and pending[member].brightness == intent.brightness
                and all(
                    pending[member].policies[attribute].owner
                    is candidate.owners.get(attribute)
                    and self._permitted(
                        pending[member].policies[attribute].owner,
                        member,
                        attribute,
                    )
                    for attribute in intent.policies
                )
                and all(
                    attribute in pending[member].explicit
                    or self._intent_permitted(member, pending[member], attribute)
                    for attribute in (
                        LightControlAttributes.BRIGHTNESS,
                        LightControlAttributes.COLOR,
                    )
                    if attribute in intent.attributes
                )
                and self._combinable(pending[member])
                and self._compatible(member, intent.parameters)
                for member in members
            )
        )

    def _intent_permitted(
        self,
        member: str,
        intent: NativeIntent,
        attribute: LightControlAttributes,
    ) -> bool:
        """Computed fallback retains source and member guards for its own attribute."""
        policy = intent.policies[attribute]
        return (
            policy.version
            == self.adaptive_versions.get(policy.owner, {}).get(member, 0)
            and self._permitted(policy.owner, member, attribute)
            and attribute
            in self.manager.get_adaption_control_attributes(
                policy.owner,
                intent.source,
            )
        )

    async def _send(
        self,
        entity: str,
        intent: NativeIntent,
        parent: Context,
        members: Iterable[str] = (),
    ) -> None:
        context = self.manager.create_context("native_group", parent=parent)
        context.user_id = parent.user_id
        policy = intent.policies.get(LightControlAttributes.BRIGHTNESS)
        brightness = (
            intent.brightness
            if (
                LightControlAttributes.BRIGHTNESS in intent.explicit
                or (
                    policy is not None
                    and policy.owner.is_on
                    and LightControlAttributes.BRIGHTNESS
                    in self.manager.get_adaption_control_attributes(
                        policy.owner,
                        entity,
                    )
                    and all(
                        LightControlAttributes.BRIGHTNESS
                        in self.manager.get_adaption_control_attributes(
                            policy.owner,
                            member,
                        )
                        for member in (*members, intent.source)
                    )
                )
            )
            else {}
        )
        if not brightness and not intent.colour:
            return
        data = {ATTR_ENTITY_ID: entity, **brightness, **intent.colour}
        self.manager.last_service_data[entity] = {
            **self.manager.last_service_data.get(entity, {}),
            **data,
        }
        await self.hass.services.async_call(
            "light",
            SERVICE_TURN_ON,
            data,
            blocking=True,
            context=context,
        )
