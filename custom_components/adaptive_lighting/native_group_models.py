"""Plans, execution status and report claims for native light requests."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, NamedTuple

from .adaptation_utils import LightControlAttributes

if TYPE_CHECKING:
    import asyncio

    from homeassistant.core import Context

    from .switch import AdaptiveSwitch

type Parameters = Mapping[str, Any]
type LightRequests = Mapping[str, Parameters]


def _snapshot_parameters(parameters: Parameters) -> Parameters:
    """Detach scalar and flat colour-vector parameters from mutable payloads."""
    return MappingProxyType(
        {
            key: tuple(value) if isinstance(value, list) else value
            for key, value in parameters.items()
        },
    )


@dataclass(frozen=True)
class NativeGroup:
    """Unambiguous owners for each attribute and the current native members."""

    owners: Mapping[LightControlAttributes, AdaptiveSwitch]
    members: frozenset[str]

    def __post_init__(self) -> None:
        """Freeze the independent attribute owners with the membership snapshot."""
        object.__setattr__(self, "owners", MappingProxyType(dict(self.owners)))


@dataclass(frozen=True)
class AttributePolicy:
    """One attribute's adaptation profile and captured settings revision."""

    owner: AdaptiveSwitch
    version: int


@dataclass(frozen=True)
class NativeIntent:
    """An immutable member intent, including its independent generations."""

    colour: Parameters
    explicit: LightControlAttributes
    version: int
    source: str
    policies: Mapping[LightControlAttributes, AttributePolicy]
    brightness: Parameters = field(default_factory=dict)
    brightness_wait: float | None = None

    def __post_init__(self) -> None:
        """Detach payloads from mutable preparation and dispatch dictionaries."""
        object.__setattr__(self, "colour", _snapshot_parameters(self.colour))
        object.__setattr__(self, "brightness", _snapshot_parameters(self.brightness))
        object.__setattr__(self, "policies", MappingProxyType(dict(self.policies)))

    @property
    def attributes(self) -> LightControlAttributes:
        """The independent attributes for which this intent carries a command."""
        return (
            LightControlAttributes.COLOR if self.colour else LightControlAttributes.NONE
        ) | (
            LightControlAttributes.BRIGHTNESS
            if self.brightness
            else LightControlAttributes.NONE
        )

    def select(self, attributes: LightControlAttributes) -> NativeIntent:
        """Retain only selected attributes without changing request identity."""
        return replace(
            self,
            colour=self.colour if LightControlAttributes.COLOR in attributes else {},
            brightness=(
                self.brightness
                if LightControlAttributes.BRIGHTNESS in attributes
                else {}
            ),
            explicit=self.explicit & attributes,
            policies={
                attribute: policy
                for attribute, policy in self.policies.items()
                if attribute in attributes
            },
            brightness_wait=(
                self.brightness_wait
                if LightControlAttributes.COLOR in attributes
                else None
            ),
        )

    @property
    def switch(self) -> AdaptiveSwitch:
        """Return the shared profile after combination eligibility is established."""
        return next(iter(self.policies.values())).owner

    @property
    def parameters(self) -> Parameters:
        """Combine attributes after their timing compatibility has been checked."""
        return {**self.brightness, **self.colour}


@dataclass(frozen=True)
class NativePlan:
    """Complete intent, fixed before the original service starts dispatching."""

    context: Context
    requests: LightRequests
    groups: Mapping[str, NativeGroup]
    intents: Mapping[str, NativeIntent]

    def __post_init__(self) -> None:
        """Freeze the complete request snapshot after preparation finishes."""
        object.__setattr__(
            self,
            "requests",
            MappingProxyType(
                {
                    entity: _snapshot_parameters(data)
                    for entity, data in self.requests.items()
                },
            ),
        )
        object.__setattr__(self, "groups", MappingProxyType(dict(self.groups)))
        object.__setattr__(self, "intents", MappingProxyType(dict(self.intents)))


@dataclass(frozen=True)
class DispatchDecision:
    """Original-handler payload and whether it owns this target's attributes."""

    params: Parameters | None
    forwarded: LightControlAttributes = LightControlAttributes.NONE


@dataclass
class BatchExecution:
    """Mutable outcomes; forwarding attributes is distinct from accepting power."""

    forwarded: dict[str, LightControlAttributes] = field(default_factory=dict)
    accepted_members: set[str] = field(default_factory=set)
    failed_members: set[str] = field(default_factory=set)
    errors: list[BaseException] = field(default_factory=list)
    children: set[asyncio.Future[None]] = field(default_factory=set)
    closed: bool = False
    aborted: bool = False

    def forward(
        self,
        members: Iterable[str],
        attributes: LightControlAttributes,
    ) -> None:
        """The original handler owns these attributes before its result is known."""
        for member in members:
            self.forwarded[member] = (
                self.forwarded.get(member, LightControlAttributes.NONE) | attributes
            )

    def accept(self, members: Iterable[str]) -> None:
        """The original handler accepted the target; deferred brightness may supply power."""
        self.accepted_members.update(members)

    def retire(self, members: Iterable[str]) -> None:
        """Unsuccessful or unobserved members must not be recovered or retried."""
        self.failed_members.update(members)

    def abort(self) -> None:
        """Cancellation or unrecoverable failure invalidates every report claim."""
        self.aborted = True

    def close(self) -> None:
        """End the invocation while keeping successful late-report claims valid."""
        self.closed = True
        # _run has already selected the exception to propagate. Late claims
        # need outcome flags, not traceback frames retaining the original plan.
        self.errors.clear()


@dataclass(frozen=True)
class NativeBatch:
    """An invocation pairs a fixed plan with its independently owned outcomes."""

    plan: NativePlan
    execution: BatchExecution = field(default_factory=BatchExecution)


@dataclass(frozen=True)
class AdaptiveRevision:
    """A computed adaptation claim is valid only for this owner's member revision."""

    owner: AdaptiveSwitch
    member: str
    version: int
    attributes: LightControlAttributes


@dataclass(frozen=True)
class ActivationClaim:
    """One expected report, without retaining the whole request plan."""

    execution: BatchExecution
    request_versions: tuple[tuple[str, int], ...]
    adaptive_revisions: tuple[AdaptiveRevision, ...]
    attributes: LightControlAttributes
    aggregate_only: bool
    required_context_id: str | None = None


class ActivationCoverage(NamedTuple):
    """Axes already covered by one consumed activation claim."""

    colour: bool = False
    brightness: bool = False
    aggregate_only: bool = False
