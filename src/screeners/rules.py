"""Composable screening rule primitives.

The screener has several profile-specific criteria, but the execution shape is
stable: evaluate named rules, count diagnostics, and only require a subset of
rules for final pass/fail.  These small primitives keep that orchestration
separate from the CAN SLIM-specific rule definitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol


@dataclass(frozen=True)
class RuleResult:
    """Result from evaluating one named screening rule."""

    name: str
    passed: bool
    required: bool = True


class ScreeningRule(Protocol):
    """Strategy interface for one screening rule."""

    name: str
    required: bool

    def evaluate(self, company: Mapping[str, Any]) -> RuleResult:
        """Evaluate *company* and return a named pass/fail result."""


@dataclass(frozen=True)
class CallableRule:
    """Screening rule backed by a callable predicate."""

    name: str
    predicate: Callable[[Mapping[str, Any]], bool]
    required: bool = True

    def evaluate(self, company: Mapping[str, Any]) -> RuleResult:
        return RuleResult(
            name=self.name,
            passed=bool(self.predicate(company)),
            required=self.required,
        )


@dataclass(frozen=True)
class ScreeningEvaluation:
    """Overall evaluation for one company."""

    passed: bool
    results: dict[str, bool]


class ScreeningEngine:
    """Evaluate companies against a sequence of rule strategies."""

    def __init__(self, rules: list[ScreeningRule]):
        self.rules = list(rules)

    @property
    def rule_names(self) -> list[str]:
        return [rule.name for rule in self.rules]

    def evaluate(self, company: Mapping[str, Any]) -> ScreeningEvaluation:
        rule_results = [rule.evaluate(company) for rule in self.rules]
        required_results = [result for result in rule_results if result.required]
        return ScreeningEvaluation(
            passed=all(result.passed for result in required_results),
            results={result.name: result.passed for result in rule_results},
        )
