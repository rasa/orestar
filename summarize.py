from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

import pandas as pd


LINCOLN_COUNTY_ZIPS: set[str] = {
    "97498",  # Yachats
    "97394",  # Waldport
    "97391",  # Toledo
    "97390",  # Tidewater
    "97366",  # South Beach
    "97380",  # Siletz
    "97376",  # Seal Rock
    "97369",  # Otter Rock
    "97368",  # Otis
    "97365",  # Newport
    "97364",  # Neotsu
    "97357",  # Logsden
    "97367",  # Lincoln City
    "97388",  # Gleneden Beach
    "97343",  # Eddyville
    "97341",  # Depoe Bay
    "97326",  # Blodgett
    "97324",  # Alsea
}

RELEVANT_SUBTYPES: set[str] = {
    "Cash Contribution",
    "In-Kind Contribution",
    "Loan Received (Non-Exempt)",
}

MISC_CASH_SMALL_LABEL = "Miscellaneous Cash Contributions $100 and under"
MISC_IN_KIND_SMALL_LABEL = "Miscellaneous In-Kind Contributions $100 and under"

MISC_CASH_DISPLAY_LABEL = "Misc. Cash Contributions up to $100"
MISC_IN_KIND_DISPLAY_LABEL = "Misc. In-Kind Contributions up to $100"

CUTOFF_DATE: date = date(2025, 7, 1)


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


class VoterPartyLookup:
    def __init__(self) -> None:
        self.by_exact_name: Dict[str, str] = {}
        self.by_last_and_first_initial: Dict[Tuple[str, str], Optional[str]] = {}

    @classmethod
    def from_file(cls, path: Path) -> "VoterPartyLookup":
        lookup = cls()
        if not path.exists():
            return lookup

        lines = path.read_text(encoding="utf-8").splitlines()
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) < 2:
                parts = line.split()

            if len(parts) < 2:
                continue

            party = parts[-1].strip().upper()
            name = " ".join(parts[:-1]).strip()
            if not name or not party:
                continue

            lookup._add_entry(name, party)

        return lookup

    def _add_entry(self, name: str, party: str) -> None:
        exact_key = self._normalize_name(name)
        if exact_key:
            self.by_exact_name[exact_key] = party

        fallback_key = self._last_and_first_initial_key(name)
        if fallback_key is None:
            return

        if fallback_key not in self.by_last_and_first_initial:
            self.by_last_and_first_initial[fallback_key] = party
        else:
            existing = self.by_last_and_first_initial[fallback_key]
            if existing != party:
                self.by_last_and_first_initial[fallback_key] = None

    def party_for_name(self, name: str) -> Optional[str]:
        exact_key = self._normalize_name(name)
        if exact_key in self.by_exact_name:
            return self.by_exact_name[exact_key]

        fallback_key = self._last_and_first_initial_key(name)
        if fallback_key is None:
            return None

        return self.by_last_and_first_initial.get(fallback_key)

    def append_party(self, name: str) -> str:
        party = self.party_for_name(name)
        if not party:
            return name
        if name.endswith(f" ({party})"):
            return name
        return f"{name} ({party})"

    def _normalize_name(self, name: str) -> str:
        cleaned = " ".join(name.strip().upper().replace(",", " ").split())
        return cleaned

    def _last_and_first_initial_key(self, name: str) -> Optional[Tuple[str, str]]:
        tokens = [token for token in name.strip().upper().replace(",", " ").split() if token]
        if len(tokens) < 2:
            return None
        first_initial = tokens[0][0]
        last_name = tokens[-1]
        return last_name, first_initial


class CampaignFinanceReportBuilder:
    def __init__(self, input_dir: Path, output_dir: Path, voter_lookup: VoterPartyLookup) -> None:
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.voter_lookup = voter_lookup

    def build_reports(self, filenames: Sequence[str]) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

        summaries: List[CandidateSummary] = []

        for filename in filenames:
            input_path = self.input_dir / filename
            rows = self._read_rows(input_path)

            report_text = self._format_candidate_report(rows, input_path.name)
            output_path = self.output_dir / f"{input_path.stem}-report.txt"
            output_path.write_text(report_text, encoding="utf-8")

            summaries.append(self._build_candidate_summary(rows, input_path.name))

        summary_amount_report_text = self._format_summary_report(summaries)
        (self.output_dir / "summary-report.txt").write_text(
            summary_amount_report_text,
            encoding="utf-8",
        )

        summary_pct_report_text = self._format_summary_percentage_report(summaries)
        (self.output_dir / "summary-percentages-report.txt").write_text(
            summary_pct_report_text,
            encoding="utf-8",
        )

    def _read_rows(self, path: Path) -> List[ReportRow]:
        df = pd.read_excel(path, engine="xlrd", dtype=str).fillna("")

        df = df[df["Sub Type"].isin(RELEVANT_SUBTYPES)].copy()
        df = df[df["Tran Date"].apply(self._is_on_or_after_cutoff)].copy()
        df = self._remove_superseded_amended_rows(df)

        grouped: Dict[str, AggregatedContributor] = {}

        for _, raw_row in df.iterrows():
            contributor_payee = raw_row.get("Contributor/Payee", "").strip()
            if not contributor_payee:
                continue

            amount = self._parse_decimal(raw_row.get("Amount", "0"))
            aggregate_amount = self._parse_decimal(raw_row.get("Aggregate Amount", "0"))

            city = raw_row.get("City", "").strip()
            state = raw_row.get("State", "").strip().upper()
            zip_code = self._normalize_zip(raw_row.get("Zip", ""))

            emp_name = self._derive_emp_name(
                emp_name=raw_row.get("Emp Name", ""),
                employ_ind=raw_row.get("Employ Ind", ""),
                self_employ_ind=raw_row.get("Self Employ Ind", ""),
            )

            is_misc_small, misc_display_label = self._classify_misc_small(contributor_payee)
            key = contributor_payee.lower()

            if key not in grouped:
                grouped[key] = AggregatedContributor(
                    contributor_payee=contributor_payee,
                    amount_sum=amount,
                    max_aggregate_amount=aggregate_amount,
                    contribution_count=1,
                    city=city,
                    state=state,
                    zip_code=zip_code,
                    emp_name=emp_name,
                    is_misc_small=is_misc_small,
                    misc_display_label=misc_display_label,
                )
            else:
                existing = grouped[key]
                existing.amount_sum += amount
                if aggregate_amount > existing.max_aggregate_amount:
                    existing.max_aggregate_amount = aggregate_amount
                existing.contribution_count += 1
                existing.city = self._pick_value(existing.city, city)
                existing.state = self._pick_value(existing.state, state)
                existing.zip_code = self._pick_value(existing.zip_code, zip_code)
                existing.emp_name = self._pick_emp_name(existing.emp_name, emp_name)
                existing.is_misc_small = existing.is_misc_small or is_misc_small
                if misc_display_label:
                    existing.misc_display_label = misc_display_label

        rows: List[ReportRow] = []
        for item in grouped.values():
            final_amount = max(item.amount_sum, item.max_aggregate_amount)

            if item.is_misc_small:
                display_name = f"{item.misc_display_label} ({item.contribution_count})"
                in_state = "n/a"
                in_county = "n/a"
            else:
                display_name = item.contributor_payee
                in_state, in_county = self._derive_location_flags(
                    amount=final_amount,
                    state=item.state,
                    zip_code=item.zip_code,
                )

            rows.append(
                ReportRow(
                    in_state=in_state,
                    in_county=in_county,
                    contributor_payee=self.voter_lookup.append_party(display_name),
                    amount=final_amount,
                    city=item.city,
                    state=item.state,
                )
            )

        rows.sort(
            key=lambda row: (
                self._sort_bucket(row.in_state),
                self._sort_bucket(row.in_county),
                -row.amount,
                row.contributor_payee.lower(),
            )
        )
        return rows

    def _build_candidate_summary(self, rows: Sequence[ReportRow], filename: str) -> CandidateSummary:
        candidate_name, seat = self._candidate_name_and_seat_from_filename(filename)

        inside_county = Decimal("0")
        outside_county = Decimal("0")
        inside_oregon = Decimal("0")
        outside_oregon = Decimal("0")
        not_known = Decimal("0")

        for row in rows:
            if row.in_county == "Yes":
                inside_county += row.amount
            if row.in_county == "No":
                outside_county += row.amount
            if row.in_state == "Yes":
                inside_oregon += row.amount
            if row.in_state == "No":
                outside_oregon += row.amount
            if row.in_state == "n/a" or row.in_county == "n/a":
                not_known += row.amount

        return CandidateSummary(
            candidate=self.voter_lookup.append_party(candidate_name),
            seat=seat,
            inside_county=inside_county,
            outside_county=outside_county,
            inside_oregon=inside_oregon,
            outside_oregon=outside_oregon,
            not_known=not_known,
        )

    def _classify_misc_small(self, contributor_payee: str) -> Tuple[bool, str]:
        normalized = contributor_payee.strip().lower()
        if normalized == MISC_CASH_SMALL_LABEL.lower():
            return True, MISC_CASH_DISPLAY_LABEL
        if normalized == MISC_IN_KIND_SMALL_LABEL.lower():
            return True, MISC_IN_KIND_DISPLAY_LABEL
        return False, ""

    def _remove_superseded_amended_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        original_ids_to_remove: Set[str] = set()

        for _, row in df.iterrows():
            tran_status = row.get("Tran Status", "").strip().lower()
            if tran_status != "amended":
                continue

            original_id = row.get("Original Id", "").strip()
            if original_id:
                original_ids_to_remove.add(original_id)

        if not original_ids_to_remove:
            return df

        tran_ids = df["Tran Id"].astype(str).str.strip()
        return df[~tran_ids.isin(original_ids_to_remove)].copy()

    def _is_on_or_after_cutoff(self, value: object) -> bool:
        parsed = self._parse_date(value)
        if parsed is None:
            return False
        return parsed >= CUTOFF_DATE

    def _parse_date(self, value: object) -> Optional[date]:
        text = str(value).strip()
        if not text:
            return None

        for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%m-%d-%y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                pass

        try:
            parsed = pd.to_datetime(text, errors="coerce")
            if pd.isna(parsed):
                return None
            return parsed.date()
        except Exception:
            return None

    def _derive_emp_name(
        self,
        emp_name: str,
        employ_ind: str,
        self_employ_ind: str,
    ) -> str:
        employ_ind_clean = employ_ind.strip().upper()
        self_employ_ind_clean = self_employ_ind.strip().upper()
        emp_name_clean = emp_name.strip()

        if self_employ_ind_clean == "Y":
            return "Self"
        if employ_ind_clean == "N":
            return "None"
        return emp_name_clean

    def _derive_location_flags(
        self,
        amount: Decimal,
        state: str,
        zip_code: str,
    ) -> Tuple[str, str]:
        if amount <= Decimal("100.00"):
            return "n/a", "n/a"

        in_state = "Yes" if state == "OR" else "No"
        in_county = "Yes" if zip_code in LINCOLN_COUNTY_ZIPS else "No"
        return in_state, in_county

    def _normalize_zip(self, zip_value: str) -> str:
        text = str(zip_value).strip()
        if not text:
            return ""
        if "." in text:
            text = text.split(".", 1)[0]
        if "-" in text:
            text = text.split("-", 1)[0]
        return text[:5]

    def _parse_decimal(self, value: object) -> Decimal:
        cleaned = str(value).replace(",", "").replace("$", "").strip()
        if cleaned == "":
            return Decimal("0")
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return Decimal("0")

    def _pick_value(self, existing: str, new_value: str) -> str:
        if existing.strip():
            return existing
        return new_value.strip()

    def _pick_emp_name(self, existing: str, new_value: str) -> str:
        existing_clean = existing.strip()
        new_clean = new_value.strip()

        if existing_clean == "Self":
            return existing_clean
        if new_clean == "Self":
            return new_clean

        if existing_clean == "None":
            return existing_clean if not new_clean else new_clean
        if new_clean == "None":
            return existing_clean if existing_clean else new_clean

        if existing_clean:
            return existing_clean
        return new_clean

    def _sort_bucket(self, value: str) -> int:
        order = {
            "Yes": 0,
            "No": 1,
            "n/a": 2,
        }
        return order.get(value, 99)

    def _format_candidate_report(self, rows: Sequence[ReportRow], filename: str) -> str:
        title = self._report_title_from_filename(filename)

        headers_top: Tuple[str, ...] = (
            "In",
            "In",
            "Contributor/Payee",
            "Amount",
            "City",
            "State",
        )
        headers_bottom: Tuple[str, ...] = (
            "Oregon?",
            "County?",
            "",
            "",
            "",
            "",
        )

        data_rows: List[List[str]] = [
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

        parts: List[str] = [
            f"{title}:",
            "ORESTAR Contributions",
            "As of May 4, 2026",
            "",
            self._format_mixed_line(headers_top, widths, numeric_cols=set()),
            self._format_mixed_line(headers_bottom, widths, numeric_cols=set()),
            self._format_separator(widths),
        ]

        current_group: Optional[Tuple[str, str]] = None
        subtotal = Decimal("0")
        grand_total = Decimal("0")
        numeric_cols = {3}

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

    def _format_summary_report(self, summaries: Sequence[CandidateSummary]) -> str:
        headers_top: Tuple[str, ...] = (
            "Candidate",
            "Seat",
            "Inside",
            "Outside",
            "Inside",
            "Outside",
            "Not",
            "Total",
        )
        headers_bottom: Tuple[str, ...] = (
            "",
            "",
            "County",
            "County",
            "Oregon",
            "Oregon",
            "Known",
            "",
        )
        numeric_cols = {2, 3, 4, 5, 6, 7}

        data_rows: List[List[str]] = [
            [
                summary.candidate,
                summary.seat,
                self._format_money(summary.inside_county),
                self._format_money(summary.outside_county),
                self._format_money(summary.inside_oregon),
                self._format_money(summary.outside_oregon),
                self._format_money(summary.not_known),
                self._format_money(summary.total),
            ]
            for summary in summaries
        ]

        total_inside_county = sum((s.inside_county for s in summaries), Decimal("0"))
        total_outside_county = sum((s.outside_county for s in summaries), Decimal("0"))
        total_inside_oregon = sum((s.inside_oregon for s in summaries), Decimal("0"))
        total_outside_oregon = sum((s.outside_oregon for s in summaries), Decimal("0"))
        total_not_known = sum((s.not_known for s in summaries), Decimal("0"))
        total_all = sum((s.total for s in summaries), Decimal("0"))

        total_row: List[str] = [
            "Total",
            "",
            self._format_money(total_inside_county),
            self._format_money(total_outside_county),
            self._format_money(total_inside_oregon),
            self._format_money(total_outside_oregon),
            self._format_money(total_not_known),
            self._format_money(total_all),
        ]

        widths = self._compute_widths(headers_top, headers_bottom, data_rows + [total_row])

        parts: List[str] = [
            "Summary Report",
            "ORESTAR Contributions",
            "As of May 4, 2026",
            "",
            self._format_mixed_line(headers_top, widths, numeric_cols=set()),
            self._format_mixed_line(headers_bottom, widths, numeric_cols=set()),
            self._format_separator(widths),
        ]

        for summary in summaries:
            parts.append(
                self._format_mixed_line(
                    (
                        summary.candidate,
                        summary.seat,
                        self._format_money(summary.inside_county),
                        self._format_money(summary.outside_county),
                        self._format_money(summary.inside_oregon),
                        self._format_money(summary.outside_oregon),
                        self._format_money(summary.not_known),
                        self._format_money(summary.total),
                    ),
                    widths,
                    numeric_cols=numeric_cols,
                )
            )

        parts.append(self._format_separator(widths))
        parts.append(self._format_mixed_line(total_row, widths, numeric_cols=numeric_cols))

        return "\n".join(parts) + "\n"

    def _format_summary_percentage_report(self, summaries: Sequence[CandidateSummary]) -> str:
        headers_top: Tuple[str, ...] = (
            "Candidate",
            "Seat",
            "Inside",
            "Outside",
            "Inside",
            "Outside",
            "Not",
            "Total",
        )
        headers_bottom: Tuple[str, ...] = (
            "",
            "",
            "County",
            "County",
            "Oregon",
            "Oregon",
            "Known",
            "",
        )
        numeric_cols = {2, 3, 4, 5, 6, 7}

        data_rows: List[List[str]] = [
            [
                summary.candidate,
                summary.seat,
                self._format_percent(summary.inside_county, summary.total),
                self._format_percent(summary.outside_county, summary.total),
                self._format_percent(summary.inside_oregon, summary.total),
                self._format_percent(summary.outside_oregon, summary.total),
                self._format_percent(summary.not_known, summary.total),
                self._format_percent(summary.total, summary.total),
            ]
            for summary in summaries
        ]

        count = Decimal(len(summaries)) if summaries else Decimal("0")

        avg_inside_county = self._average([s.inside_county / s.total * Decimal("100") if s.total else Decimal("0") for s in summaries], count)
        avg_outside_county = self._average([s.outside_county / s.total * Decimal("100") if s.total else Decimal("0") for s in summaries], count)
        avg_inside_oregon = self._average([s.inside_oregon / s.total * Decimal("100") if s.total else Decimal("0") for s in summaries], count)
        avg_outside_oregon = self._average([s.outside_oregon / s.total * Decimal("100") if s.total else Decimal("0") for s in summaries], count)
        avg_not_known = self._average([s.not_known / s.total * Decimal("100") if s.total else Decimal("0") for s in summaries], count)

        average_row: List[str] = [
            "Average",
            "",
            self._format_percent_value(avg_inside_county),
            self._format_percent_value(avg_outside_county),
            self._format_percent_value(avg_inside_oregon),
            self._format_percent_value(avg_outside_oregon),
            self._format_percent_value(avg_not_known),
            self._format_percent_value(Decimal("100.0") if summaries else Decimal("0.0")),
        ]

        widths = self._compute_widths(headers_top, headers_bottom, data_rows + [average_row])

        parts: List[str] = [
            "Summary Percentage Report",
            "ORESTAR Contributions",
            "As of May 4, 2026",
            "",
            self._format_mixed_line(headers_top, widths, numeric_cols=set()),
            self._format_mixed_line(headers_bottom, widths, numeric_cols=set()),
            self._format_separator(widths),
        ]

        for summary in summaries:
            parts.append(
                self._format_mixed_line(
                    (
                        summary.candidate,
                        summary.seat,
                        self._format_percent(summary.inside_county, summary.total),
                        self._format_percent(summary.outside_county, summary.total),
                        self._format_percent(summary.inside_oregon, summary.total),
                        self._format_percent(summary.outside_oregon, summary.total),
                        self._format_percent(summary.not_known, summary.total),
                        self._format_percent(summary.total, summary.total),
                    ),
                    widths,
                    numeric_cols=numeric_cols,
                )
            )

        parts.append(self._format_separator(widths))
        parts.append(self._format_mixed_line(average_row, widths, numeric_cols=numeric_cols))

        return "\n".join(parts) + "\n"

    def _average(self, values: Sequence[Decimal], count: Decimal) -> Decimal:
        if count == Decimal("0"):
            return Decimal("0")
        return sum(values, Decimal("0")) / count

    def _format_percent(self, numerator: Decimal, denominator: Decimal) -> str:
        if denominator == Decimal("0"):
            return "0.0%"
        value = (numerator / denominator) * Decimal("100")
        return self._format_percent_value(value)

    def _format_percent_value(self, value: Decimal) -> str:
        rounded = value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return f"{rounded:.1f}%"

    def _candidate_name_and_seat_from_filename(self, filename: str) -> Tuple[str, str]:
        stem = Path(filename).stem
        parts = stem.split("-")
        if len(parts) < 4:
            return stem, ""

        seat = f"Seat {parts[1]}"
        first_name = parts[2].capitalize()
        last_name = parts[3].capitalize()
        return f"{first_name} {last_name}", seat

    def _report_title_from_filename(self, filename: str) -> str:
        candidate_name, seat = self._candidate_name_and_seat_from_filename(filename)
        candidate_name = self.voter_lookup.append_party(candidate_name)
        if seat:
            return f"{candidate_name} ({seat})"
        return candidate_name

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

    def _format_money(self, amount: Decimal) -> str:
        return f"{amount:,.2f}"

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
            (
                group[0],
                group[1],
                "Total",
                self._format_money(subtotal),
                "",
                "",
            ),
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
            (
                "",
                "",
                "Grand Total",
                self._format_money(grand_total),
                "",
                "",
            ),
            widths,
            numeric_cols=numeric_cols,
        )


def main() -> None:
    input_dir = Path(".")
    output_dir = Path(".")
    voters_path = input_dir / "voters.txt"

    filenames = [
        "seat-1-casey-miller.xls",
        "seat-1-cathie-rigby.xls",
        "seat-1-cheri-brubaker.xls",
        "seat-2-cristen-don.xls",
        "seat-3-curtis-landers.xls",
        "seat-3-walter-chuck.xls",
    ]

    voter_lookup = VoterPartyLookup.from_file(voters_path)
    builder = CampaignFinanceReportBuilder(
        input_dir=input_dir,
        output_dir=output_dir,
        voter_lookup=voter_lookup,
    )
    builder.build_reports(filenames)


if __name__ == "__main__":
    main()
