#!/usr/bin/env python3
"""campaign_builder.py"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

import pandas as pd

from campaign_charts import CampaignChartWriter
from campaign_config import (
    CUTOFF_DATE,
    LINCOLN_COUNTY_ZIPS,
    MISC_CASH_DISPLAY_LABEL,
    MISC_CASH_SMALL_LABEL,
    MISC_IN_KIND_DISPLAY_LABEL,
    MISC_IN_KIND_SMALL_LABEL,
    PARTY_ORDER,
    RELEVANT_SUBTYPES,
)
from campaign_models import AggregatedContributor, CandidatePartySummary, CandidateSummary, ReportRow
from campaign_reports import CampaignReportFormatter
from voter_party import VoterPartyLookup


class CampaignFinanceReportBuilder:
    def __init__(self, input_dir: Path, output_dir: Path, voter_lookup: VoterPartyLookup) -> None:
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.voter_lookup = voter_lookup
        self.formatter = CampaignReportFormatter(output_dir)
        self.chart_writer = CampaignChartWriter(output_dir)

    def build_reports(self, filenames: Sequence[str]) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

        summaries: List[CandidateSummary] = []
        party_summaries: List[CandidatePartySummary] = []

        for filename in filenames:
            input_path = self.input_dir / filename
            rows = self._read_rows(input_path)

            title = self._report_title_from_filename(input_path.name)
            report_text = self.formatter.format_candidate_report(rows, title)

            output_path = self.output_dir / f"{input_path.stem}-report.txt"
            output_path.write_text(report_text, encoding="utf-8")

            summaries.append(self._build_candidate_summary(rows, input_path.name))
            party_summaries.append(self._build_candidate_party_summary(rows, input_path.name))

        summary_report_path = self.output_dir / "summary-report.txt"
        summary_report_path.write_text(self.formatter.format_summary_report(summaries), encoding="utf-8")
        self._append_summary_footer(summary_report_path)

        (self.output_dir / "summary-percentages-report.txt").write_text(
            self.formatter.format_summary_percentage_report(summaries),
            encoding="utf-8",
        )

        self.formatter.write_summary_percentage_csv(summaries)
        self.formatter.write_candidate_party_summary_csv(party_summaries)

        self.chart_writer.generate_summary_charts(summaries)
        self.chart_writer.generate_candidate_party_charts(party_summaries)

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
                donor_party = "UNK"
            else:
                display_name = item.contributor_payee
                in_state, in_county = self._derive_location_flags(
                    amount=final_amount,
                    state=item.state,
                    zip_code=item.zip_code,
                )
                donor_party = self.voter_lookup.party_for_name(item.contributor_payee) or "UNK"

            rows.append(
                ReportRow(
                    in_state=in_state,
                    in_county=in_county,
                    contributor_payee=self.voter_lookup.append_party(display_name),
                    amount=final_amount,
                    city=item.city,
                    state=item.state,
                    donor_party=donor_party,
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
        outside_oregon = Decimal("0")
        not_known = Decimal("0")

        for row in rows:
            if row.in_state == "Yes" and row.in_county == "Yes":
                inside_county += row.amount
            elif row.in_state == "Yes" and row.in_county == "No":
                outside_county += row.amount
            elif row.in_state == "No":
                outside_oregon += row.amount
            else:
                not_known += row.amount

        inside_oregon = inside_county + outside_county

        return CandidateSummary(
            candidate=self.voter_lookup.append_party(candidate_name),
            seat=seat,
            inside_county=inside_county,
            outside_county=outside_county,
            inside_oregon=inside_oregon,
            outside_oregon=outside_oregon,
            not_known=not_known,
        )

    def _build_candidate_party_summary(
        self,
        rows: Sequence[ReportRow],
        filename: str,
    ) -> CandidatePartySummary:
        candidate_name, seat = self._candidate_name_and_seat_from_filename(filename)
        candidate_name = self.voter_lookup.append_party(candidate_name)

        totals: Dict[str, Decimal] = {party_code: Decimal("0") for party_code in PARTY_ORDER}

        for row in rows:
            party_code = row.donor_party if row.donor_party in totals else "UNK"
            totals[party_code] += row.amount

        return CandidatePartySummary(
            candidate=candidate_name,
            seat=seat,
            dem=totals["DEM"],
            rep=totals["REP"],
            ind=totals["IND"],
            nav=totals["NAV"],
            unk=totals["UNK"],
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

    def _derive_emp_name(self, emp_name: str, employ_ind: str, self_employ_ind: str) -> str:
        employ_ind_clean = employ_ind.strip().upper()
        self_employ_ind_clean = self_employ_ind.strip().upper()
        emp_name_clean = emp_name.strip()

        if self_employ_ind_clean == "Y":
            return "Self"
        if employ_ind_clean == "N":
            return "None"
        return emp_name_clean

    def _derive_location_flags(self, amount: Decimal, state: str, zip_code: str) -> Tuple[str, str]:
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
        order = {"Yes": 0, "No": 1, "n/a": 2}
        return order.get(value, 99)

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

    def _append_summary_footer(self, summary_report_path: Path) -> None:
        footer_path = self.input_dir / "summary-footer.txt"
        if not footer_path.exists():
            return

        footer_text = footer_path.read_text(encoding="utf-8")
        with summary_report_path.open("a", newline="\n", encoding="utf-8") as f:
            f.write("\n")
            f.write(footer_text)
            if not footer_text.endswith("\n"):
                f.write("\n")
