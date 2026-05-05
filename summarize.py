#!/usr/bin/env python3
"""summarize.py"""

from __future__ import annotations

from pathlib import Path

from campaign_builder import CampaignFinanceReportBuilder
from voter_party import VoterPartyLookup


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
