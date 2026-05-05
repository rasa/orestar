#!/usr/bin/env python3
"""campaign_charts.py"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Sequence

import matplotlib.pyplot as plt
import numpy as np

from campaign_config import PARTY_COLORS, PARTY_LABELS
from campaign_models import CandidatePartySummary, CandidateSummary


class CampaignChartWriter:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def generate_summary_charts(self, summaries: Sequence[CandidateSummary]) -> None:
        if not summaries:
            return

        candidates = [summary.candidate for summary in summaries]

        inside_county = np.array([float(summary.inside_county) for summary in summaries])
        outside_county = np.array([float(summary.outside_county) for summary in summaries])
        outside_oregon = np.array([float(summary.outside_oregon) for summary in summaries])
        not_known = np.array([float(summary.not_known) for summary in summaries])

        x = np.arange(len(candidates))
        width = 0.7

        plt.figure(figsize=(14, 8))
        plt.bar(x, inside_county, width, label="Inside Lincoln County")
        plt.bar(x, outside_county, width, bottom=inside_county, label="Outside County / Inside Oregon")
        plt.bar(x, outside_oregon, width, bottom=inside_county + outside_county, label="Outside Oregon")
        plt.bar(
            x,
            not_known,
            width,
            bottom=inside_county + outside_county + outside_oregon,
            label="Unknown / Misc.",
        )

        plt.xticks(x, candidates, rotation=20, ha="right")
        plt.ylabel("Dollars")
        plt.title("Where Campaign Money Is Coming From")
        plt.legend()
        plt.tight_layout()
        plt.savefig(self.output_dir / "campaign-money-by-source.png", dpi=200)
        plt.close()

        inside_county_pct = np.array([float(self._pct_value(s.inside_county, s.total)) for s in summaries])
        outside_county_pct = np.array([float(self._pct_value(s.outside_county, s.total)) for s in summaries])
        outside_oregon_pct = np.array([float(self._pct_value(s.outside_oregon, s.total)) for s in summaries])
        not_known_pct = np.array([float(self._pct_value(s.not_known, s.total)) for s in summaries])

        plt.figure(figsize=(14, 8))
        plt.bar(x, inside_county_pct, width, label="Inside Lincoln County")
        plt.bar(x, outside_county_pct, width, bottom=inside_county_pct, label="Outside County / Inside Oregon")
        plt.bar(
            x,
            outside_oregon_pct,
            width,
            bottom=inside_county_pct + outside_county_pct,
            label="Outside Oregon",
        )
        plt.bar(
            x,
            not_known_pct,
            width,
            bottom=inside_county_pct + outside_county_pct + outside_oregon_pct,
            label="Unknown / Misc.",
        )

        plt.xticks(x, candidates, rotation=20, ha="right")
        plt.ylabel("Percent of Total")
        plt.title("Share of Campaign Money by Source")
        plt.ylim(0, 100)
        plt.legend()
        plt.tight_layout()
        plt.savefig(self.output_dir / "campaign-money-by-source-percent.png", dpi=200)
        plt.close()

    def generate_candidate_party_charts(self, party_summaries: Sequence[CandidatePartySummary]) -> None:
        if not party_summaries:
            return

        candidates = [summary.candidate for summary in party_summaries]

        dem = np.array([float(summary.dem) for summary in party_summaries])
        rep = np.array([float(summary.rep) for summary in party_summaries])
        ind = np.array([float(summary.ind) for summary in party_summaries])
        nav = np.array([float(summary.nav) for summary in party_summaries])
        unk = np.array([float(summary.unk) for summary in party_summaries])

        x = np.arange(len(candidates))
        width = 0.7

        plt.figure(figsize=(14, 8))
        plt.bar(x, dem, width, label=PARTY_LABELS["DEM"], color=PARTY_COLORS["DEM"])
        plt.bar(x, rep, width, bottom=dem, label=PARTY_LABELS["REP"], color=PARTY_COLORS["REP"])
        plt.bar(x, ind, width, bottom=dem + rep, label=PARTY_LABELS["IND"], color=PARTY_COLORS["IND"])
        plt.bar(x, nav, width, bottom=dem + rep + ind, label=PARTY_LABELS["NAV"], color=PARTY_COLORS["NAV"])
        plt.bar(x, unk, width, bottom=dem + rep + ind + nav, label=PARTY_LABELS["UNK"], color=PARTY_COLORS["UNK"])

        plt.xticks(x, candidates, rotation=20, ha="right")
        plt.ylabel("Dollars")
        plt.title("Campaign Contributions by Donor Party")
        plt.legend()
        plt.tight_layout()
        plt.savefig(self.output_dir / "campaign-money-by-candidate-donor-party.png", dpi=200)
        plt.close()

        totals = dem + rep + ind + nav + unk
        dem_pct = self._safe_percent_array(dem, totals)
        rep_pct = self._safe_percent_array(rep, totals)
        ind_pct = self._safe_percent_array(ind, totals)
        nav_pct = self._safe_percent_array(nav, totals)
        unk_pct = self._safe_percent_array(unk, totals)

        plt.figure(figsize=(14, 8))
        plt.bar(x, dem_pct, width, label=PARTY_LABELS["DEM"], color=PARTY_COLORS["DEM"])
        plt.bar(x, rep_pct, width, bottom=dem_pct, label=PARTY_LABELS["REP"], color=PARTY_COLORS["REP"])
        plt.bar(x, ind_pct, width, bottom=dem_pct + rep_pct, label=PARTY_LABELS["IND"], color=PARTY_COLORS["IND"])
        plt.bar(
            x,
            nav_pct,
            width,
            bottom=dem_pct + rep_pct + ind_pct,
            label=PARTY_LABELS["NAV"],
            color=PARTY_COLORS["NAV"],
        )
        plt.bar(
            x,
            unk_pct,
            width,
            bottom=dem_pct + rep_pct + ind_pct + nav_pct,
            label=PARTY_LABELS["UNK"],
            color=PARTY_COLORS["UNK"],
        )

        plt.xticks(x, candidates, rotation=20, ha="right")
        plt.ylabel("Percent of Total")
        plt.title("Share of Contributions by Donor Party")
        plt.ylim(0, 100)
        plt.legend()
        plt.tight_layout()
        plt.savefig(self.output_dir / "campaign-money-by-candidate-donor-party-percent.png", dpi=200)
        plt.close()

    def _safe_percent_array(self, values: np.ndarray, totals: np.ndarray) -> np.ndarray:
        return np.divide(
            values * 100.0,
            totals,
            out=np.zeros_like(values, dtype=float),
            where=totals != 0,
        )

    def _pct_value(self, numerator: Decimal, denominator: Decimal) -> Decimal:
        if denominator == Decimal("0"):
            return Decimal("0.0")
        return ((numerator / denominator) * Decimal("100")).quantize(
            Decimal("0.1"),
            rounding=ROUND_HALF_UP,
        )