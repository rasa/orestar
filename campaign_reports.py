#!/usr/bin/env python3
"""campaign_reports.py"""

from __future__ import annotations

import csv
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import List, Sequence, Set, Tuple

from campaign_models import CandidatePartySummary, CandidateSummary, ReportRow


class CampaignReportFormatter:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def format_candidate_report(self, rows: Sequence[ReportRow], title: str) -> str:
        headers_top = ("In", "In", "Contributor/Payee", "Amount", "City", "State")
        headers_bottom = ("Oregon?", "County?", "", "", "", "")
        numeric_cols = {3}

        data_rows = [
            [
                row.in_state,
                row.in_county,
                row.contributor_payee,
                self._format_money(row.amount),
                row.city,
                row.state,
            ]
            for row in rows
        ]

        widths = self._compute_widths(headers_top, headers_bottom, data_rows)

        parts = [
            f"{title}:",
            "ORESTAR Contributions",
            "As of May 4, 2026",
            "",
            self._format_mixed_line(headers_top, widths, numeric_cols=set()),
            self._format_mixed_line(headers_bottom, widths, numeric_cols=set()),
            self._format_separator(widths),
        ]

        current_group: Tuple[str, str] | None = None
        subtotal = Decimal("0")
        grand_total = Decimal("0")

        for row in rows:
            group = (row.in_state, row.in_county)

            if current_group is None:
                current_group = group
            elif group != current_group:
                parts.append(self._format_candidate_total_line(current_group, subtotal, widths, numeric_cols))
                parts.append("")
                subtotal = Decimal("0")
                current_group = group

            parts.append(
                self._format_mixed_line(
                    (
                        row.in_state,
                        row.in_county,
                        row.contributor_payee,
                        self._format_money(row.amount),
                        row.city,
                        row.state,
                    ),
                    widths,
                    numeric_cols=numeric_cols,
                )
            )

            subtotal += row.amount
            grand_total += row.amount

        if current_group is not None:
            parts.append(self._format_candidate_total_line(current_group, subtotal, widths, numeric_cols))

        parts.append("")
        parts.append(self._format_candidate_grand_total_line(grand_total, widths, numeric_cols))

        return "\n".join(parts) + "\n"

    def format_summary_report(self, summaries: Sequence[CandidateSummary]) -> str:
        headers_top = ("Candidate", "Seat", "Inside", "Outside", "Inside", "Outside", "Not", "Total")
        headers_bottom = ("", "", "County", "County", "Oregon", "Oregon", "Known", "")
        numeric_cols = {2, 3, 4, 5, 6, 7}

        data_rows = [
            [
                s.candidate,
                s.seat,
                self._format_money(s.inside_county),
                self._format_money(s.outside_county),
                self._format_money(s.inside_oregon),
                self._format_money(s.outside_oregon),
                self._format_money(s.not_known),
                self._format_money(s.total),
            ]
            for s in summaries
        ]

        total_row = [
            "Total",
            "",
            self._format_money(sum((s.inside_county for s in summaries), Decimal("0"))),
            self._format_money(sum((s.outside_county for s in summaries), Decimal("0"))),
            self._format_money(sum((s.inside_oregon for s in summaries), Decimal("0"))),
            self._format_money(sum((s.outside_oregon for s in summaries), Decimal("0"))),
            self._format_money(sum((s.not_known for s in summaries), Decimal("0"))),
            self._format_money(sum((s.total for s in summaries), Decimal("0"))),
        ]

        widths = self._compute_widths(headers_top, headers_bottom, data_rows + [total_row])

        parts = [
            "Summary Report",
            "ORESTAR Contributions",
            "As of May 4, 2026",
            "",
            self._format_mixed_line(headers_top, widths, numeric_cols=set()),
            self._format_mixed_line(headers_bottom, widths, numeric_cols=set()),
            self._format_separator(widths),
        ]

        for row in data_rows:
            parts.append(self._format_mixed_line(row, widths, numeric_cols=numeric_cols))

        parts.append(self._format_separator(widths))
        parts.append(self._format_mixed_line(total_row, widths, numeric_cols=numeric_cols))

        return "\n".join(parts) + "\n"

    def format_summary_percentage_report(self, summaries: Sequence[CandidateSummary]) -> str:
        headers_top = ("Candidate", "Seat", "Inside", "Outside", "Inside", "Outside", "Not", "Total")
        headers_bottom = ("", "", "County", "County", "Oregon", "Oregon", "Known", "")
        numeric_cols = {2, 3, 4, 5, 6, 7}

        data_rows = [
            [
                s.candidate,
                s.seat,
                self._format_percent(s.inside_county, s.total),
                self._format_percent(s.outside_county, s.total),
                self._format_percent(s.inside_oregon, s.total),
                self._format_percent(s.outside_oregon, s.total),
                self._format_percent(s.not_known, s.total),
                self._format_percent(s.total, s.total),
            ]
            for s in summaries
        ]

        count = Decimal(len(summaries)) if summaries else Decimal("0")

        average_row = [
            "Average",
            "",
            self._format_percent_value(self._average([self._pct_value(s.inside_county, s.total) for s in summaries], count)),
            self._format_percent_value(self._average([self._pct_value(s.outside_county, s.total) for s in summaries], count)),
            self._format_percent_value(self._average([self._pct_value(s.inside_oregon, s.total) for s in summaries], count)),
            self._format_percent_value(self._average([self._pct_value(s.outside_oregon, s.total) for s in summaries], count)),
            self._format_percent_value(self._average([self._pct_value(s.not_known, s.total) for s in summaries], count)),
            self._format_percent_value(Decimal("100.0") if summaries else Decimal("0.0")),
        ]

        widths = self._compute_widths(headers_top, headers_bottom, data_rows + [average_row])

        parts = [
            "Summary Percentage Report",
            "ORESTAR Contributions",
            "As of May 4, 2026",
            "",
            self._format_mixed_line(headers_top, widths, numeric_cols=set()),
            self._format_mixed_line(headers_bottom, widths, numeric_cols=set()),
            self._format_separator(widths),
        ]

        for row in data_rows:
            parts.append(self._format_mixed_line(row, widths, numeric_cols=numeric_cols))

        parts.append(self._format_separator(widths))
        parts.append(self._format_mixed_line(average_row, widths, numeric_cols=numeric_cols))

        return "\n".join(parts) + "\n"

    def write_summary_percentage_csv(self, summaries: Sequence[CandidateSummary]) -> None:
        output_path = self.output_dir / "summary-percentages-report.csv"

        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "Candidate",
                    "Seat",
                    "Inside County %",
                    "Outside County %",
                    "Inside Oregon %",
                    "Outside Oregon %",
                    "Not Known %",
                    "Total %",
                ]
            )

            for s in summaries:
                writer.writerow(
                    [
                        s.candidate,
                        s.seat,
                        f"{self._pct_value(s.inside_county, s.total):.1f}",
                        f"{self._pct_value(s.outside_county, s.total):.1f}",
                        f"{self._pct_value(s.inside_oregon, s.total):.1f}",
                        f"{self._pct_value(s.outside_oregon, s.total):.1f}",
                        f"{self._pct_value(s.not_known, s.total):.1f}",
                        "100.0" if s.total else "0.0",
                    ]
                )

    def write_candidate_party_summary_csv(self, party_summaries: Sequence[CandidatePartySummary]) -> None:
        output_path = self.output_dir / "candidate-party-summary.csv"

        with output_path.open("w", newline="\n", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "Candidate",
                    "Seat",
                    "Democrat",
                    "Republican",
                    "OR Independent Party",
                    "Non-affiliated",
                    "Not Known",
                    "Total",
                ]
            )

            for s in party_summaries:
                writer.writerow(
                    [
                        s.candidate,
                        s.seat,
                        self._format_money(s.dem),
                        self._format_money(s.rep),
                        self._format_money(s.ind),
                        self._format_money(s.nav),
                        self._format_money(s.unk),
                        self._format_money(s.total),
                    ]
                )

    def _average(self, values: Sequence[Decimal], count: Decimal) -> Decimal:
        if count == Decimal("0"):
            return Decimal("0")
        return sum(values, Decimal("0")) / count

    def _pct_value(self, numerator: Decimal, denominator: Decimal) -> Decimal:
        if denominator == Decimal("0"):
            return Decimal("0.0")
        return ((numerator / denominator) * Decimal("100")).quantize(
            Decimal("0.1"),
            rounding=ROUND_HALF_UP,
        )

    def _format_percent(self, numerator: Decimal, denominator: Decimal) -> str:
        return self._format_percent_value(self._pct_value(numerator, denominator))

    def _format_percent_value(self, value: Decimal) -> str:
        rounded = value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return f"{rounded:.1f}%"

    def _format_money(self, amount: Decimal) -> str:
        return f"{amount:,.2f}"

    def _compute_widths(
        self,
        headers_top: Sequence[str],
        headers_bottom: Sequence[str],
        data_rows: Sequence[Sequence[str]],
    ) -> List[int]:
        widths = [0] * len(headers_top)

        for i, value in enumerate(headers_top):
            widths[i] = max(widths[i], len(value))

        for i, value in enumerate(headers_bottom):
            widths[i] = max(widths[i], len(value))

        for row in data_rows:
            for i, value in enumerate(row):
                widths[i] = max(widths[i], len(value))

        return widths

    def _format_separator(self, widths: Sequence[int]) -> str:
        return "  ".join("-" * width for width in widths)

    def _format_mixed_line(
        self,
        values: Sequence[str],
        widths: Sequence[int],
        numeric_cols: Set[int],
    ) -> str:
        parts: List[str] = []
        for i, value in enumerate(values):
            if i in numeric_cols:
                parts.append(value.rjust(widths[i]))
            else:
                parts.append(value.ljust(widths[i]))
        return "  ".join(parts)

    def _format_candidate_total_line(
        self,
        group: Tuple[str, str],
        subtotal: Decimal,
        widths: Sequence[int],
        numeric_cols: Set[int],
    ) -> str:
        return self._format_mixed_line(
            (group[0], group[1], "Total", self._format_money(subtotal), "", ""),
            widths,
            numeric_cols=numeric_cols,
        )

    def _format_candidate_grand_total_line(
        self,
        grand_total: Decimal,
        widths: Sequence[int],
        numeric_cols: Set[int],
    ) -> str:
        return self._format_mixed_line(
            ("", "", "Grand Total", self._format_money(grand_total), "", ""),
            widths,
            numeric_cols=numeric_cols,
        )
        