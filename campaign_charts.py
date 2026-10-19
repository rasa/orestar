#!/usr/bin/env python3
"""Charts for ORESTAR contribution reports.

The brown segment identifies the candidate's own contributions, already included
in the geographic and donor-party totals. The listed values should be reconciled
with the latest ORESTAR exports whenever the reports are updated.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Sequence

import matplotlib.pyplot as plt
import numpy as np

from campaign_config import PARTY_COLORS, PARTY_LABELS
from campaign_models import CandidatePartySummary, CandidateSummary

INSIDE_COUNTY_COLOR = "#78B878" # friendly green
OUTSIDE_COUNTY_COLOR = "#F0A0BE" # Warm pink
OUTSIDE_OREGON_COLOR = "#E87872" # Soft corel red
UNKNOWN_COLOR = "#A8ADB2" # Neutral gray
SELF_CONTRIBUTION_COLOR = "#76C9BD" # Soft turquoise

THRESHOLD = 0.04

# Candidate's own contributions listed in ORESTAR reports as of October 18, 2026.
# These amounts are ALREADY included in the summary data. Do not add them to totals.
# Each entry contains (donor party, own contributions in dollars).
CANDIDATE_OWN_CONTRIBUTIONS = {
    "Joe Steere": ("REP", Decimal("4200.00")), # include's his wife's $1,200 contribution
    "Casey Miller": ("NAV", Decimal("2052.32")),
    "Cathie Rigby": ("DEM", Decimal("978.45")),
    "Catherine Rigby": ("DEM", Decimal("978.45")),  # alternative name
    "Cristen Don": ("DEM", Decimal("152.00")),
}


class CampaignChartWriter:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    @staticmethod
    def _own_contributions(candidates: Sequence[str]) -> tuple[np.ndarray, list[str | None]]:
        values = []
        parties = []
        for display_name in candidates:
            name = display_name.split(" (", 1)[0].strip()
            party, amount = CANDIDATE_OWN_CONTRIBUTIONS.get(name, (None, Decimal("0")))
            values.append(float(amount))
            parties.append(party)
        return np.array(values, dtype=float), parties

    @staticmethod
    def _subtract_checked(
        original: np.ndarray, amounts: np.ndarray, candidates: Sequence[str], category: str
    ) -> np.ndarray:
        if np.any(original + 0.001 < amounts):
            bad = [candidates[i] for i in np.flatnonzero(original + 0.001 < amounts)]
            raise ValueError(
                f"Candidate contributions exceed the {category} category for {bad}. "
                "Review CANDIDATE_OWN_CONTRIBUTIONS against current ORESTAR data."
            )
        return original - amounts

    def generate_summary_charts(self, summaries: Sequence[CandidateSummary]) -> None:
        if not summaries:
            return

        candidates = [summary.candidate for summary in summaries]
        inside = np.array([float(s.inside_county) for s in summaries])
        outside = np.array([float(s.outside_county) for s in summaries])
        out_of_state = np.array([float(s.outside_oregon) for s in summaries])
        unknown = np.array([float(s.not_known) for s in summaries])
        self_amount, _ = self._own_contributions(candidates)

        # All four candidate contributions currently appear as inside-county.
        # Remove them from green before displaying the same dollars in brown.
        inside_excluding_self = self._subtract_checked(
            inside, self_amount, candidates, "Inside Lincoln County"
        )
        amounts = [inside_excluding_self, outside, out_of_state, unknown, self_amount]
        labels = [
            "Inside Lincoln County (other donors)",
            "Outside County / Inside Oregon",
            "Outside Oregon",
            "Unknown / Misc.",
            "Candidate's Own Contributions",
        ]
        colors = [
            INSIDE_COUNTY_COLOR,
            OUTSIDE_COUNTY_COLOR,
            OUTSIDE_OREGON_COLOR,
            UNKNOWN_COLOR,
            SELF_CONTRIBUTION_COLOR,
        ]

        self._draw_chart(
            candidates, amounts, labels, colors,
            title="Where Campaign Money Is Coming From",
            filename="campaign-money-by-source.png",
            percent=False,
        )
        self._draw_chart(
            candidates, amounts, labels, colors,
            title="Share of Campaign Money by Source",
            filename="campaign-money-by-source-percent.png",
            percent=True,
        )

    def generate_candidate_party_charts(
        self, party_summaries: Sequence[CandidatePartySummary]
    ) -> None:
        if not party_summaries:
            return

        candidates = [summary.candidate for summary in party_summaries]
        parties = ["DEM", "REP", "IND", "NAV", "UNK"]
        data = {
            "DEM": np.array([float(s.dem) for s in party_summaries]),
            "REP": np.array([float(s.rep) for s in party_summaries]),
            "IND": np.array([float(s.ind) for s in party_summaries]),
            "NAV": np.array([float(s.nav) for s in party_summaries]),
            "UNK": np.array([float(s.unk) for s in party_summaries]),
        }
        self_amount, self_party = self._own_contributions(candidates)

        # Remove each candidate's contribution from their donor-party segment
        # before displaying it separately in brown; totals stay unchanged.
        for party in parties:
            deductions = np.array(
                [amount if candidate_party == party else 0.0
                 for amount, candidate_party in zip(self_amount, self_party)],
                dtype=float,
            )
            data[party] = self._subtract_checked(
                data[party], deductions, candidates, PARTY_LABELS[party]
            )

        amounts = [data[party] for party in parties] + [self_amount]
        labels = [PARTY_LABELS[party] for party in parties] + ["Candidate's Own Contributions"]
        colors = [PARTY_COLORS[party] for party in parties] + [SELF_CONTRIBUTION_COLOR]

        self._draw_chart(
            candidates, amounts, labels, colors,
            title="Campaign Contributions by Donor Party",
            filename="campaign-money-by-candidate-donor-party.png",
            percent=False,
        )
        self._draw_chart(
            candidates, amounts, labels, colors,
            title="Share of Contributions by Donor Party",
            filename="campaign-money-by-candidate-donor-party-percent.png",
            percent=True,
        )

    def _draw_chart(
        self,
        candidates: Sequence[str],
        amounts: Sequence[np.ndarray],
        labels: Sequence[str],
        colors: Sequence[str],
        title: str,
        filename: str,
        percent: bool,
    ) -> None:
        x = np.arange(len(candidates))
        width = 0.7
        totals = np.sum(np.array(amounts), axis=0)
        displayed = (
            [self._safe_percent_array(values, totals) for values in amounts]
            if percent else amounts
        )

        fig, ax = plt.subplots(figsize=(10, 10))
        bottoms = np.zeros(len(candidates), dtype=float)
        for values, label, color in zip(displayed, labels, colors):
            ax.bar(x, values, width, bottom=bottoms, label=label, color=color)
            bottoms += values

        threshold = THRESHOLD * 100 if percent else float(np.max(totals)) * THRESHOLD
        self._add_stacked_value_labels(
            ax, x, displayed, amounts, totals, width, threshold
        )
        if not percent:
            self._add_bar_totals(ax, x, totals)
        else:
            ax.set_ylim(0, 100)

        ax.set_xlim(-0.48, x[-1] + 0.95)
        ax.set_xticks(x)
        ax.set_xticklabels(candidates, rotation=20, ha="right")
        ax.set_ylabel("Percent of Total" if percent else "Dollars")
        ax.set_title(title)
        ax.legend()
        fig.tight_layout(pad=0.7)
        fig.savefig(self.output_dir / filename, dpi=200)
        plt.close(fig)

    @staticmethod
    def _safe_percent_array(values: np.ndarray, totals: np.ndarray) -> np.ndarray:
        return np.divide(
            values * 100.0,
            totals,
            out=np.zeros_like(values, dtype=float),
            where=totals != 0,
        )

    def _add_stacked_value_labels(
        self,
        ax,
        x: np.ndarray,
        display_series: Sequence[np.ndarray],
        amount_series: Sequence[np.ndarray],
        totals: np.ndarray,
        width: float,
        inside_threshold: float,
    ) -> None:
        cumulative = np.zeros(len(x), dtype=float)
        for display_values, amount_values in zip(display_series, amount_series):
            percents = self._safe_percent_array(amount_values, totals)
            for i, (display_value, amount_value, pct, bottom) in enumerate(
                zip(display_values, amount_values, percents, cumulative)
            ):
                if display_value <= 0 or amount_value <= 0 or totals[i] <= 0:
                    continue

                inline_label = f"${amount_value:,.0f} ({pct:.0f}%)"
                side_label = f"${amount_value:,.0f} ({pct:.0f}%)"
                y = bottom + display_value / 2.0
                if display_value >= inside_threshold:
                    ax.text(
                        x[i], y, inline_label,
                        ha="center", va="center", fontsize=8,
                        color="black", fontweight="bold",
                    )
                else:
                    ax.annotate(
                        side_label,
                        xy=(x[i] + width / 2, y),
                        xytext=(4, 0), textcoords="offset points",
                        ha="left", va="center", fontsize=8,
                        color="black", fontweight="bold",
                    )
            cumulative += display_values

    @staticmethod
    def _add_bar_totals(ax, x: np.ndarray, totals: np.ndarray) -> None:
        highest = float(np.max(totals)) if len(totals) else 0.0
        if highest > 0:
            ax.set_ylim(0, highest * 1.18)
        for xi, total in zip(x, totals):
            ax.annotate(
                f"${total:,.0f}", xy=(xi, total), xytext=(0, 6),
                textcoords="offset points", ha="center", va="bottom",
                fontsize=11, fontweight="bold", color="black",
            )
