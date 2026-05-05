#!/usr/bin/env python3
"""campaign_config.py"""

from __future__ import annotations

from datetime import date
from typing import Dict, List


LINCOLN_COUNTY_ZIPS: set[str] = {
    "97498", "97394", "97391", "97390", "97366", "97380",
    "97376", "97369", "97368", "97365", "97364", "97357",
    "97367", "97388", "97343", "97341", "97326", "97324",
}

RELEVANT_SUBTYPES: set[str] = {
    "Cash Contribution",
    "In-Kind Contribution",
    "Loan Received (Non-Exempt)",
}

PARTY_LABELS: Dict[str, str] = {
    "DEM": "Democrat",
    "REP": "Republican",
    "IND": "OR Independent Party",
    "NAV": "Non-affiliated",
    "UNK": "Not Known",
}

PARTY_COLORS: Dict[str, str] = {
    "DEM": "blue",
    "REP": "red",
    "IND": "violet",
    "NAV": "purple",
    "UNK": "gray",
}

PARTY_ORDER: List[str] = ["DEM", "REP", "IND", "NAV", "UNK"]

MISC_CASH_SMALL_LABEL = "Miscellaneous Cash Contributions $100 and under"
MISC_IN_KIND_SMALL_LABEL = "Miscellaneous In-Kind Contributions $100 and under"

MISC_CASH_DISPLAY_LABEL = "Misc. Cash Contributions up to $100"
MISC_IN_KIND_DISPLAY_LABEL = "Misc. In-Kind Contributions up to $100"

CUTOFF_DATE: date = date(2025, 7, 1)


# Add campaign committees, PACs, unions, caucuses, or organizations here.
# Keys are normalized internally, so capitalization/punctuation is not critical.
DONOR_PARTY_OVERRIDES: Dict[str, str] = {
    "May and Done": "DEM",
    "Democratic Party of Oregon": "DEM",
    "Democratic Party of Oregon (353)": "DEM",
    "Lincoln County Democrats": "DEM",
    "Democratic Party of Lincoln County": "DEM",

    "Oregon Republican Party": "REP",
    "Republican Party of Oregon": "REP",
    "Lincoln County Republicans": "REP",
    "Republican Party of Lincoln County": "REP",

    "Independent Party of Oregon": "IND",
}
