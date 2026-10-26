"""Romanian Wikipedia live search via the MediaWiki API."""

import urllib.parse
import requests

from infact.common.results import SearchResult
from infact.tools.search.search_api import SearchAPI


class RoWikiSearchAPI(SearchAPI):
    """Searches Romanian Wikipedia (ro.wikipedia.org) using the live MediaWiki API."""
    name = "wiki_ro"
    is_free = True
    is_local = False

    _API_URL = "https://ro.wikipedia.org/w/api.php"
    # Wikimedia respinge cu 403 cererile fără User-Agent descriptiv
    _HEADERS = {"User-Agent": "SNACTS-RO/1.0 (serviciu de fact-checking; proiect de cercetare)"}

    def _call_api(self, query: str, limit: int) -> list[SearchResult]:
        # Strip quotes that cause 403 errors on the MediaWiki API
        query = query.replace('"', '').replace("'", '')

        results = self._search(query, limit)
        if results:
            return results

        # Fallback (Faza 3.3): full-text search often fails on long, sentence-like
        # queries; retry with only the main entities (proper nouns + numbers)
        shortened = self._shorten_to_entities(query)
        if shortened and shortened.lower() != query.lower():
            if self.logger:
                self.logger.log(
                    f"[wiki_ro] 0 rezultate pentru „{query}” — "
                    f"reîncerc cu entitățile principale: „{shortened}”"
                )
            results = self._search(shortened, limit)
        return results

    @staticmethod
    def _shorten_to_entities(query: str) -> str:
        """Keeps only capitalized words and numbers — the likely entities."""
        tokens = [t.strip(".,;:!?()[]") for t in query.split()]
        entities = []
        for t in tokens:
            if t and (t[:1].isupper() or t[:1].isdigit()) and t not in entities:
                entities.append(t)
        if not entities:
            # No entities detected: keep the first few content words instead
            entities = [t for t in tokens if len(t) > 3][:4]
        return " ".join(entities[:6])

    def _search(self, query: str, limit: int) -> list[SearchResult]:
        results = []

        # Step 1: full-text search to find matching page titles
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
            "srprop": "snippet",
            "format": "json",
            "utf8": 1,
        }
        try:
            resp = requests.get(self._API_URL, params=search_params, headers=self._HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            if self.logger:
                self.logger.log(f"[wiki_ro] Search request failed: {e}")
            return results

        hits = data.get("query", {}).get("search", [])
        if not hits:
            return results

        # Step 2: fetch intro extracts for each matched page
        page_ids = "|".join(str(h["pageid"]) for h in hits[:limit])
        extract_params = {
            "action": "query",
            "pageids": page_ids,
            "prop": "extracts|info",
            "exintro": True,
            "explaintext": True,
            "exsentences": 5,
            "inprop": "url",
            "format": "json",
            "utf8": 1,
        }
        try:
            resp2 = requests.get(self._API_URL, params=extract_params, headers=self._HEADERS, timeout=10)
            resp2.raise_for_status()
            data2 = resp2.json()
        except Exception as e:
            if self.logger:
                self.logger.log(f"[wiki_ro] Extract request failed: {e}")
            return results

        pages = data2.get("query", {}).get("pages", {})
        for pid_str, page in pages.items():
            title = page.get("title", "")
            extract = page.get("extract", "").strip()
            url = page.get("fullurl", f"https://ro.wikipedia.org/wiki/{urllib.parse.quote(title)}")
            if extract:
                text = f"{title}: {extract}"
                results.append(SearchResult(source=url, text=text))

        return results
