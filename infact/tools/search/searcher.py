import re
from typing import Any

import numpy as np

from config.globals import api_keys
from infact.common.action import WebSearch, WikiDumpLookup, WikiLookup, RoWikiLookup, Search
from infact.common.results import SearchResult
from infact.tools.search.duckduckgo import DuckDuckGo
from infact.tools.search.knowledge_base import KnowledgeBase
from infact.tools.search.query_serper import SerperAPI
from infact.tools.search.search_api import SearchAPI
from infact.tools.search.wiki_dump import WikiDumpAPI
from infact.tools.search.wiki_ro import RoWikiSearchAPI
from infact.tools.source_ranker import SourceRanker
from infact.tools.tool import Tool

SEARCH_APIS = {
    "google": SerperAPI,
    "duckduckgo": DuckDuckGo,
    "wiki_dump": WikiDumpAPI,
    "averitec_kb": KnowledgeBase,
    "wiki_ro": RoWikiSearchAPI,
}


class Searcher(Tool):
    """Searches the specified resource (Google, Wikipedia, ...) for evidence. Takes
    a list of specified search engines. The list defines the precedence of the search
    engines meaning that if search_engine[0] did not yield any results, search_engine[1]
    will be tried next."""
    name = "searcher"
    search_apis: dict[str, SearchAPI]
    stats: dict[str, int]

    def __init__(self,
                 search_engine_config: dict[str, dict] = None,
                 summarize: bool = True,
                 max_searches: int = 5,
                 limit_per_search: int = 5,
                 max_result_len: int = None,  # chars
                 do_debug: bool = False,
                 **kwargs):
        super().__init__(**kwargs)

        if search_engine_config is None:
            search_engine = "google" if api_keys["serper_api_key"] else "duckduckgo"
            self.logger.log(f"Niciun motor de căutare specificat. Se folosește {search_engine} + wiki_ro.")
            search_engine_config = {search_engine: {}, "wiki_ro": {}}

        # Add device to knowledge base kwargs
        if "averitec_kb" in search_engine_config:
            search_engine_config["averitec_kb"].update(dict(device=self.device))

        # Setup search APIs
        self.search_apis = {se: SEARCH_APIS[se](logger=self.logger, **kwargs)
                            for se, kwargs in search_engine_config.items()}

        # Register available tools
        actions = []
        available_apis = self.search_apis.keys()
        if "wiki_dump" in available_apis:
            actions.append(WikiDumpLookup)
        if "google" in available_apis or "duckduckgo" in available_apis or "averitec_kb" in available_apis:
            actions.append(WebSearch)
        if "wiki_ro" in available_apis:
            actions.append(RoWikiLookup)
        self.actions = actions

        # Etichetarea credibilității surselor (Faza E1)
        self.source_ranker = SourceRanker()

        self.summarize = summarize
        self.max_searches = max_searches
        self.limit_per_search = limit_per_search
        self.max_result_len = max_result_len  # chars

        self.debug = do_debug

        self.past_queries_helpful: dict[str, bool] = {}
        # Cut the result text, maintaining a little buffer for the summary prompt
        self.past_search_results = set()

        self.reset()

    def perform(self, action: Search) -> list[SearchResult]:
        return self.search(action.query)

    def search(self, query: str) -> list[SearchResult]:
        """Searches for evidence using the search APIs according to their precedence."""
        for search_engine in list(self.search_apis.values()):
            results = self._retrieve_search_results(query, search_engine)

            # Track search engine call
            self.stats[search_engine.name] += 1

            # Log search results info
            self.logger.log(f"S-au obținut {len(results)} rezultat(e) noi:")
            for i, result in enumerate(results):
                self.logger.log(f"\t{i + 1}. {result.source}")

            # Modify the results text to avoid jinja errors when used in prompt
            results = self._postprocess_results(results)

            # If there is at least one result, we were successful
            if len(results) > 0:
                self._register_search_results(results)
                return results
        return []

    def _remove_known_search_results(self, results: list[SearchResult]) -> list[SearchResult]:
        """Removes already known search results"""
        return [r for r in results if r not in self.past_search_results]

    def _register_search_results(self, results: list[SearchResult]):
        """Adds the provided list of results to the set of known results."""
        self.past_search_results |= set(results)

    def reset(self):
        """Removes all known search results and resets the statistics."""
        self.past_search_results = set()
        self.stats = {s.name: 0 for s in self.search_apis.values()}

    def _retrieve_search_results(
            self,
            query: str,
            search_engine: SearchAPI,
    ) -> list[SearchResult]:
        # Run the search
        results = search_engine.search(query, self.limit_per_search)
        self.past_queries_helpful[query] = True

        # Remove already known results
        return self._remove_known_search_results(results)

    def _postprocess_results(self, results: list[SearchResult]) -> list[SearchResult]:
        """Modifies the results text to avoid jinja errors when used in prompt.
        Also annotates each result with its source credibility tier (Faza E1)."""
        for result in results:
            result.text = self.postprocess_result(result.text)
            rating = self.source_ranker.rate_url(result.source)
            result.tier = rating.tier.value
            result.trust_score = rating.score
        return results

    def postprocess_result(self, result: str):
        """Removes all double curly braces to avoid conflicts with Jinja and optionally truncates
        the result text to a maximum length."""
        result = re.sub(r"\{\{.*}}", "", result)
        if self.max_result_len is not None:
            result = result[self.max_result_len:]
        return result

    def get_stats(self) -> dict[str, Any]:
        total_searches = np.sum([n for n in self.stats.values()])
        return {
            "Total searches": total_searches,
            "Search engine calls": self.stats,
        }
