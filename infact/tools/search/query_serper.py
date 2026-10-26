# Copyright 2024 Google LLC
# Major modifications applied by Technical University of Darmstadt, FG Multimodal Grounded Learning.

"""Class for querying the Google Serper API."""

import random
import re
import time
from datetime import date, datetime, timedelta
from typing import Any, Optional, Literal

import requests

from infact.common.results import SearchResult
from infact.tools.search.remote_search_api import RemoteSearchAPI
from config.globals import api_keys

_SERPER_URL = 'https://google.serper.dev'
NO_RESULT_MSG = 'No good Google Search result was found'

# Month abbreviations (English + Romanian) for parsing Serper publication dates
_MONTH_ABBREVS = {
    "jan": 1, "ian": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "mai": 5,
    "jun": 6, "iun": 6, "jul": 7, "iul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "noi": 11, "dec": 12,
}

# Relative dates: "3 days ago" / "acum 3 zile"
_RELATIVE_DATE_RE = re.compile(
    r"(?:acum\s+)?(\d+)\s+"
    r"(hour|hours|ore|oră|ora|day|days|zi|zile|week|weeks|săptămân\w*|saptaman\w*|"
    r"month|months|luni|lună|luna|year|years|an|ani)"
    r"(?:\s+ago)?",
    re.IGNORECASE,
)

_RELATIVE_UNIT_DAYS = {
    "hour": 0, "ore": 0, "oră": 0, "ora": 0,
    "day": 1, "zi": 1, "zile": 1,
    "week": 7, "săptămân": 7, "saptaman": 7,
    "month": 30, "luni": 30, "lună": 30, "luna": 30,
    "year": 365, "an": 365, "ani": 365,
}

# Absolute dates: "Feb 23, 2024" / "23 feb. 2024"
_ABSOLUTE_DATE_RE = re.compile(
    r"(?:(\d{1,2})\s+([A-Za-zăâîșț]+)\.?\s*,?\s+(\d{4}))|"
    r"(?:([A-Za-zăâîșț]+)\.?\s+(\d{1,2})\s*,?\s+(\d{4}))",
)

# Romanian keywords signaling the query targets the present state of affairs
# (word-start anchors: "factual.ro" must NOT match "actual")
_RECENCY_KEYWORDS_RE = re.compile(
    r"\b(astăzi|astazi|azi|acum|recent\w*|prezent|actual\w*|curent\w*|ultim\w*)\b",
    re.IGNORECASE,
)


def parse_result_date(raw: str) -> Optional[datetime]:
    """Best-effort parsing of the `date` field returned by Serper
    (e.g. 'Feb 23, 2024', '23 feb. 2024', '3 days ago', 'acum 3 zile', ISO)."""
    if not raw:
        return None
    raw = raw.strip()

    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass

    m = _ABSOLUTE_DATE_RE.search(raw)
    if m:
        if m.group(1):
            day_s, month_s, year_s = m.group(1), m.group(2), m.group(3)
        else:
            month_s, day_s, year_s = m.group(4), m.group(5), m.group(6)
        month = _MONTH_ABBREVS.get(month_s.lower().rstrip(".")[:4]) \
            or _MONTH_ABBREVS.get(month_s.lower()[:3])
        if month:
            try:
                return datetime(int(year_s), month, int(day_s))
            except ValueError:
                return None

    m = _RELATIVE_DATE_RE.search(raw)
    if m:
        amount = int(m.group(1))
        unit = m.group(2).lower()
        days_per_unit = next(
            (d for prefix, d in _RELATIVE_UNIT_DAYS.items() if unit.startswith(prefix)),
            None,
        )
        if days_per_unit is not None:
            return datetime.now() - timedelta(days=amount * days_per_unit)

    return None


class SerperAPI(RemoteSearchAPI):
    """Class for querying the Google Serper API."""
    name = "google"

    def __init__(self,
                 gl: str = 'ro',
                 hl: str = 'ro',
                 tbs: Optional[str] = None,
                 recency_tbs: Optional[str] = 'qdr:y',
                 search_type: Literal['news', 'search', 'places', 'images'] = 'search',
                 **kwargs):
        super().__init__(**kwargs)
        self.serper_api_key = api_keys["serper_api_key"]
        self.gl = gl
        self.hl = hl
        self.tbs = tbs
        # tbs aplicat DOAR interogărilor sensibile temporal (Faza 3.2);
        # un tbs global ar strica faptele enciclopedice
        self.recency_tbs = recency_tbs
        self.search_type = search_type
        self.total_searches = 0
        self.result_key_for_type = {
            'news': 'news',
            'places': 'places',
            'images': 'images',
            'search': 'organic',
        }

    def _call_api(self, query: str, limit: int, **kwargs: Any) -> list[SearchResult]:
        """Run query through GoogleSearch and parse result."""
        assert self.serper_api_key, 'Missing serper_api_key.'
        tbs = self.tbs
        if tbs is None and self.recency_tbs and self._is_time_sensitive(query):
            tbs = self.recency_tbs
            if self.logger:
                self.logger.log(f"[serper] Interogare sensibilă temporal — aplic tbs={tbs}: {query}")
        results = self._call_serper_api(
            query,
            gl=self.gl,
            hl=self.hl,
            num=limit,
            tbs=tbs,
            search_type=self.search_type,
            **kwargs,
        )
        return self._parse_results(results, query)

    @staticmethod
    def _is_time_sensitive(query: str) -> bool:
        """A query targets the present state of affairs if it mentions the
        current/previous year or Romanian recency keywords."""
        current_year = date.today().year
        if str(current_year) in query or str(current_year - 1) in query:
            return True
        return bool(_RECENCY_KEYWORDS_RE.search(query))

    def _call_serper_api(
            self,
            search_term: str,
            search_type: str = 'search',
            max_retries: int = 3,
            **kwargs: Any,
    ) -> dict[Any, Any]:
        """Run query through Google Serper. Returns {} on failure so the
        Searcher can fall back to the next engine instead of crashing.

        Atenție: un Response 4xx/5xx este falsy — bucla veche `while not response`
        nu incrementa num_fails la erori HTTP și se învârtea la infinit când
        Serper răspundea 400 („Not enough credits") sau 403."""
        headers = {
            'X-API-KEY': self.serper_api_key or '',
            'Content-Type': 'application/json',
        }
        params = {
            'q': search_term,
            **{key: value for key, value in kwargs.items() if value is not None},
        }
        num_fails, sleep_time = 0, 0

        while num_fails < max_retries:
            response = None
            try:
                self.total_searches += 1
                response = requests.post(
                    f'{_SERPER_URL}/{search_type}', headers=headers, params=params,
                    timeout=15,
                )
            except Exception:  # pylint: disable=broad-exception-caught
                pass

            if response is not None:
                if response.ok:
                    return response.json()
                if 400 <= response.status_code < 500:
                    # Neretriabil: cheie invalidă, credite epuizate, cerere greșită
                    if self.logger:
                        self.logger.log(
                            f"[serper] Eroare API {response.status_code} — se renunță "
                            f"(motorul următor preia căutarea): {response.text[:200]}"
                        )
                    return {}

            num_fails += 1
            sleep_time = min(sleep_time * 2, 60) or random.uniform(1, 5)
            time.sleep(sleep_time)

        if self.logger:
            self.logger.log(f"[serper] Eșec după {max_retries} încercări — 0 rezultate.")
        return {}

    def _parse_results(self, response: dict[Any, Any], query: str) -> list[SearchResult]:
        """Parse results from API response."""
        # if response.get('answerBox'):
        #     answer_box = response.get('answerBox', {})
        #     answer = answer_box.get('answer')
        #     snippet = answer_box.get('snippet')
        #     snippet_highlighted = answer_box.get('snippetHighlighted')
        #
        #     if answer and isinstance(answer, str):
        #         snippets.append(answer)
        #     if snippet and isinstance(snippet, str):
        #         snippets.append(snippet.replace('\n', ' '))
        #     if snippet_highlighted:
        #         snippets.append(snippet_highlighted)
        #
        # if response.get('knowledgeGraph'):
        #     kg = response.get('knowledgeGraph', {})
        #     title = kg.get('title')
        #     entity_type = kg.get('type')
        #     description = kg.get('description')
        #
        #     if entity_type:
        #         snippets.append(f'{title}: {entity_type}.')
        #
        #     if description:
        #         snippets.append(description)
        #
        #     for attribute, value in kg.get('attributes', {}).items():
        #         snippets.append(f'{title} {attribute}: {value}.')

        results = []
        result_key = self.result_key_for_type[self.search_type]
        if result_key in response:
            for i, result in enumerate(response[result_key]):
                if "snippet" not in result:
                    text = "NONE"
                elif "title" not in result:
                    text = f"{result['snippet']}"
                else:
                    text = f"{result['title']}: {result['snippet']}"
                url = result["link"]
                raw_date = result.get("date")
                if raw_date and text != "NONE":
                    text = f"{text} (data publicării: {raw_date})"
                results.append(SearchResult(
                    source=url,
                    text=text,
                    query=query,
                    rank=i,
                    date=parse_result_date(raw_date) if raw_date else None,
                ))

        return results
