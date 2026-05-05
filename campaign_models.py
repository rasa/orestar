
#!/usr/bin/env python3
"""campaign_models.py"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class AggregatedContributor:
    contributor_payee: str
    amount_sum: Decimal
    max_aggregate_amount: Decimal
    contribution_count: int
    city: str
    state: str
    zip_code: str
    emp_name: str
    is_misc_small: bool
    misc_display_label: str


@dataclass(frozen=True)
class ReportRow:
    in_state: str
    in_county: str
    contributor_payee: str
    amount: Decimal
    city: str
    state: str
    donor_party: str


@dataclass(frozen=True)
class CandidateSummary:
    candidate: str
    seat: str
    inside_county: Decimal
    outside_county: Decimal
    inside_oregon: Decimal
    outside_oregon: Decimal
    not_known: Decimal

    @property
    def total(self) -> Decimal:
        return self.inside_county + self.outside_county + self.not_known


@dataclass(frozen=True)
class CandidatePartySummary:
    candidate: str
    seat: str
    dem: Decimal
    rep: Decimal
    ind: Decimal
    nav: Decimal
    unk: Decimal

    @property
    def total(self) -> Decimal:
        return self.dem + self.rep + self.ind + self.nav + self.unk
