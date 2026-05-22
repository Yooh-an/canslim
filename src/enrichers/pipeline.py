"""Composable company enrichment pipeline primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence


CompanyRows = list[dict[str, Any]]


class CompanyEnricher(Protocol):
    """Strategy interface for one company enrichment step."""

    name: str

    def enrich(self, companies: Sequence[Mapping[str, Any]]) -> CompanyRows:
        """Return enriched company rows."""


@dataclass(frozen=True)
class FunctionCompanyEnricher:
    """Adapter that turns a function into a CompanyEnricher strategy."""

    name: str
    enrich_func: Callable[[Sequence[Mapping[str, Any]]], CompanyRows]
    before_message: str | None = None
    after_message: str | None = None
    progress: Callable[[str], None] | None = None

    def enrich(self, companies: Sequence[Mapping[str, Any]]) -> CompanyRows:
        if self.before_message and self.progress:
            self.progress(self.before_message)
        enriched = self.enrich_func(companies)
        if self.after_message and self.progress:
            self.progress(self.after_message)
        return enriched


class CompositeCompanyEnricher:
    """Run a sequence of enrichment strategies in order."""

    def __init__(self, enrichers: Sequence[CompanyEnricher]):
        self.enrichers = list(enrichers)

    def enrich(self, companies: Sequence[Mapping[str, Any]]) -> CompanyRows:
        enriched = [dict(company) for company in companies]
        for enricher in self.enrichers:
            enriched = enricher.enrich(enriched)
        return enriched
