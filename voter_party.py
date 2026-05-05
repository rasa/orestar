#!/usr/bin/env python3
"""voter_party.py"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from campaign_config import DONOR_PARTY_OVERRIDES


class VoterPartyLookup:
    def __init__(self) -> None:
        self.by_exact_name: Dict[str, str] = {}
        self.by_last_and_first_initial: Dict[Tuple[str, str], Optional[str]] = {}
        self.party_overrides: Dict[str, str] = {
            self._normalize_name(name): party
            for name, party in DONOR_PARTY_OVERRIDES.items()
        }

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
        normalized = self._normalize_name(name)

        if normalized in self.party_overrides:
            return self.party_overrides[normalized]

        keyword_party = self._party_from_keywords(normalized)
        if keyword_party is not None:
            return keyword_party

        if normalized in self.by_exact_name:
            return self.by_exact_name[normalized]

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

    def _party_from_keywords(self, normalized_name: str) -> Optional[str]:
        dem_patterns = [
            r"\bDEMOCRATIC\b",
            r"\bDEMOCRAT\b",
            r"\bDEMS\b",
        ]
        rep_patterns = [
            r"\bREPUBLICAN\b",
            r"\bGOP\b",
        ]
        ind_patterns = [
            r"\bINDEPENDENT PARTY\b",
        ]

        if any(re.search(pattern, normalized_name) for pattern in dem_patterns):
            return "DEM"
        if any(re.search(pattern, normalized_name) for pattern in rep_patterns):
            return "REP"
        if any(re.search(pattern, normalized_name) for pattern in ind_patterns):
            return "IND"

        return None

    def _normalize_name(self, name: str) -> str:
        cleaned = name.upper()
        cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
        cleaned = cleaned.replace(",", " ")
        cleaned = cleaned.replace(".", " ")
        cleaned = cleaned.replace("&", " AND ")
        cleaned = re.sub(r"[^A-Z0-9 ]+", " ", cleaned)
        cleaned = " ".join(cleaned.split())
        return cleaned

    def _last_and_first_initial_key(self, name: str) -> Optional[Tuple[str, str]]:
        tokens = [token for token in self._normalize_name(name).split() if token]
        if len(tokens) < 2:
            return None

        first_initial = tokens[0][0]
        last_name = tokens[-1]
        return last_name, first_initial
