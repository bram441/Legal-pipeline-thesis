"""Central registry for normalized symbolic intents (law-agnostic)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet


@dataclass(frozen=True)
class IntentSpec:
    name: str
    public: bool
    internal: bool
    stable: bool
    input_kind: str
    output_kind: str
    renderer: str
    scorable: str  # yes | partial | manual | no
    description: str


INTENT_REGISTRY: dict[str, IntentSpec] = {
    "deduction": IntentSpec(
        name="deduction",
        public=False,
        internal=True,
        stable=True,
        input_kind="predicate_boolean",
        output_kind="epistemic_boolean",
        renderer="boolean",
        scorable="yes",
        description="Check whether a grounded Boolean predicate atom is entailed, contradicted, or unknown.",
    ),
    "deduction_set": IntentSpec(
        name="deduction_set",
        public=False,
        internal=True,
        stable=True,
        input_kind="predicate_set",
        output_kind="entity_set",
        renderer="set",
        scorable="yes",
        description="Find entities for which a unary predicate is entailed.",
    ),
    "propagation": IntentSpec(
        name="propagation",
        public=True,
        internal=False,
        stable=True,
        input_kind="focus_symbols",
        output_kind="certain_facts",
        renderer="derived_facts",
        scorable="partial",
        description="Return facts/conclusions that are true or false in all models.",
    ),
    "model_expansion": IntentSpec(
        name="model_expansion",
        public=True,
        internal=False,
        stable=True,
        input_kind="focus_symbols",
        output_kind="models",
        renderer="model",
        scorable="partial",
        description="Generate one or more possible model completions.",
    ),
    "get_range": IntentSpec(
        name="get_range",
        public=True,
        internal=False,
        stable=True,
        input_kind="function_term",
        output_kind="range",
        renderer="range",
        scorable="yes",
        description="Return possible values for a function term.",
    ),
    "satisfiable": IntentSpec(
        name="satisfiable",
        public=True,
        internal=False,
        stable=True,
        input_kind="none",
        output_kind="boolean",
        renderer="satisfiable",
        scorable="yes",
        description="Check whether the KB plus case facts has at least one model.",
    ),
    "optimization": IntentSpec(
        name="optimization",
        public=True,
        internal=False,
        stable=True,
        input_kind="objective",
        output_kind="optimum",
        renderer="value",
        scorable="partial",
        description="Find a model minimizing or maximizing a valid objective term.",
    ),
    "relevance": IntentSpec(
        name="relevance",
        public=True,
        internal=False,
        stable=True,
        input_kind="focus_symbols",
        output_kind="symbols",
        renderer="symbols",
        scorable="manual",
        description="Determine relevant symbols or facts if supported by IDP-Z3.",
    ),
    "explain": IntentSpec(
        name="explain",
        public=True,
        internal=False,
        stable=True,
        input_kind="explain_target",
        output_kind="explanation",
        renderer="explanation",
        scorable="manual",
        description="Explain why a query is true/false/unknown or why the KB is inconsistent.",
    ),
}

PUBLIC_INTENT_NAMES: FrozenSet[str] = frozenset(n for n, s in INTENT_REGISTRY.items() if s.public)
INTERNAL_INTENT_NAMES: FrozenSet[str] = frozenset(n for n, s in INTENT_REGISTRY.items() if s.internal)


class UnknownIntentError(ValueError):
    pass


class IntentAccessError(ValueError):
    pass


def get_intent_spec(name: str) -> IntentSpec:
    key = (name or "").strip().lower()
    spec = INTENT_REGISTRY.get(key)
    if spec is None:
        raise UnknownIntentError("Unknown intent: " + str(name))
    return spec


def validate_intent_name(name: str, *, allow_internal: bool = False) -> str:
    key = (name or "").strip().lower()
    if not key:
        raise UnknownIntentError("Intent name is empty")
    spec = get_intent_spec(key)
    if spec.internal and not allow_internal:
        raise IntentAccessError(
            "Direct intent '" + key + "' is internal. Use type=predicate with mode=boolean or mode=set."
        )
    if not spec.public and not allow_internal:
        raise IntentAccessError("Intent '" + key + "' is not selectable as a public query intent.")
    return key


def is_public_intent(name: str) -> bool:
    return (name or "").strip().lower() in PUBLIC_INTENT_NAMES


def is_internal_intent(name: str) -> bool:
    return (name or "").strip().lower() in INTERNAL_INTENT_NAMES


def list_public_intents() -> tuple[str, ...]:
    return tuple(sorted(PUBLIC_INTENT_NAMES))


def list_stable_intents() -> tuple[str, ...]:
    return tuple(sorted(n for n, s in INTENT_REGISTRY.items() if s.stable))


def list_all_intents() -> tuple[str, ...]:
    return tuple(sorted(INTENT_REGISTRY.keys()))
