"""Source Trustworthiness Ranking System for SNACTS-RO.

Takes a list of SearchResult objects (produced by the Serper API pipeline)
and returns a per-source breakdown plus a composite TruthScore for the
overall body of evidence used in a fact-check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from urllib.parse import urlparse

from infact.common.results import SearchResult


# ─────────────────────────────────────────────────────────────────────────────
# Enums & data classes
# ─────────────────────────────────────────────────────────────────────────────

class SourceTier(str, Enum):
    TRUSTED     = "trusted"
    MIXED       = "mixed"
    UNTRUSTED   = "untrusted"
    UNKNOWN     = "unknown"


@dataclass
class SourceRating:
    """Per-source result returned by SourceRanker."""
    url: str
    domain: str
    tier: SourceTier
    score: Optional[float]          # 0-100, None when inconclusive
    reason: str                     # human-readable explanation
    occurrences: int = 1            # how many times this domain appeared

    @property
    def is_inconclusive(self) -> bool:
        return self.tier == SourceTier.UNKNOWN


@dataclass
class TruthScore:
    """Composite score for the entire evidence set of one fact-check."""
    score: Optional[float]          # 0-100, None when inconclusive
    label: str                      # human-readable label in Romanian
    confidence: str                 # "high" | "medium" | "low" | "inconclusive"
    trusted_count: int = 0
    mixed_count: int = 0
    untrusted_count: int = 0
    unknown_count: int = 0
    source_ratings: list[SourceRating] = field(default_factory=list)
    warning: Optional[str] = None   # e.g. echo-chamber or low-quality warning

    def to_dict(self) -> dict:
        """Return the aggregate credibility score only — no per-source listing.

        The internal ``source_ratings`` list is intentionally excluded from
        the public output to keep the API response lean. Use
        ``to_dict_full()`` when a detailed breakdown is needed (e.g. debug
        mode or internal logging).
        """
        return {
            "score": round(self.score, 1) if self.score is not None else None,
            "label": self.label,
            "confidence": self.confidence,
            "source_count": (
                self.trusted_count
                + self.mixed_count
                + self.untrusted_count
                + self.unknown_count
            ),
            "warning": self.warning,
        }

    def to_dict_full(self) -> dict:
        """Full breakdown including per-source ratings — for debug/logging."""
        base = self.to_dict()
        base["trusted_count"]   = self.trusted_count
        base["mixed_count"]     = self.mixed_count
        base["untrusted_count"] = self.untrusted_count
        base["unknown_count"]   = self.unknown_count
        base["sources"] = [
            {
                "url": r.url,
                "domain": r.domain,
                "tier": r.tier.value,
                "score": round(r.score, 1) if r.score is not None else None,
                "reason": r.reason,
                "occurrences": r.occurrences,
            }
            for r in self.source_ratings
        ]
        return base


# ─────────────────────────────────────────────────────────────────────────────
# Curated source lists
# ─────────────────────────────────────────────────────────────────────────────

# Score 80-100: internationally recognised, editorially independent sources
TRUSTED_SOURCES: dict[str, float] = {
    # International wire / broadcast
    "reuters.com":              100,
    "apnews.com":               100,
    "bbc.co.uk":                98,
    "bbc.com":                  98,
    "theguardian.com":          95,
    "nytimes.com":              95,
    "washingtonpost.com":       94,
    "economist.com":            95,
    "ft.com":                   95,
    "bloomberg.com":            93,
    "dw.com":                   94,
    "euronews.com":             88,
    "france24.com":             90,
    "aljazeera.com":            85,
    "npr.org":                  93,
    "pbs.org":                  92,
    # Fact-checkers
    "snopes.com":               92,
    "factcheck.org":            93,
    "politifact.com":           92,
    "fullfact.org":             92,
    "afp.com":                  95,
    "factual.ro":               88,
    "veridica.ro":              88,
    # Scientific / health
    "pubmed.ncbi.nlm.nih.gov":  99,
    "who.int":                  97,
    "cdc.gov":                  97,
    "nature.com":               98,
    "science.org":              98,
    "thelancet.com":            97,
    "nejm.org":                 97,
    # Romanian trusted sources
    "digi24.ro":                85,
    "agerpres.ro":              90,
    "mediafax.ro":              85,
    "g4media.ro":               84,
    "hotnews.ro":               83,
    "ziare.com":                78,
    "stirileprotv.ro":          82,
    "antena3.ro":               70,
    "realitatea.net":           70,
    "adevarul.ro":              80,
    "romania-insider.com":      80,
    # Government / official
    "gov.ro":                   95,
    "presidency.ro":            95,
    "mae.ro":                   94,
    "insse.ro":                 95,
    "bnr.ro":                   95,
    "europa.eu":                94,
    "un.org":                   94,
    "nato.int":                 92,
    # Wikipedia (medium-high – useful but editable)
    "ro.wikipedia.org":         72,
    "en.wikipedia.org":         72,
    "wikipedia.org":            72,
}

# Score 0-40: known misinformation, conspiracy, or propaganda outlets
UNTRUSTED_SOURCES: dict[str, float] = {
    "infowars.com":             5,
    "naturalnews.com":          8,
    "breitbart.com":            20,
    "rt.com":                   18,
    "sputniknews.com":          15,
    "sputnik.md":               15,
    "ria.ru":                   15,
    "tass.com":                 18,
    "globalresearch.ca":        10,
    "beforeitsnews.com":        5,
    "yournewswire.com":         5,
    "thegatewaypundit.com":     12,
    "zerohedge.com":            22,
    "activenews.ro":            20,
    "luju.ro":                  25,
    "flux24.ro":                22,
    "cotidianul.ro":            30,
}

# Domains considered mixed-reliability (score 41-69)
MIXED_SOURCES: dict[str, float] = {
    "dailymail.co.uk":          45,
    "nypost.com":               48,
    "foxnews.com":              42,
    "huffpost.com":             55,
    "buzzfeednews.com":         58,
    "vice.com":                 60,
    "businessinsider.com":      62,
    "mediaintelligence.ro":     55,
    "jurnalul.ro":              52,
    "evenimentulzilei.ro":      50,
    "romaniatv.net":            48,
    "antena1.ro":               55,
}

# TLDs that increase suspicion for unknown domains
_SUSPICIOUS_TLDS = {".xyz", ".click", ".top", ".win", ".loan",
                    ".gq", ".cf", ".ml", ".ga", ".tk"}

# TLDs that add credibility for unknown domains
_CREDIBLE_TLDS    = {".gov", ".edu", ".int", ".mil"}


# ─────────────────────────────────────────────────────────────────────────────
# Core ranker
# ─────────────────────────────────────────────────────────────────────────────

class SourceRanker:
    """Scores the trustworthiness of evidence sources returned by Serper.

    Usage
    -----
    ranker = SourceRanker()
    truth_score = ranker.score_results(search_results)   # list[SearchResult]
    print(truth_score.to_dict())
    """

    def __init__(self,
                 extra_trusted: dict[str, float] | None = None,
                 extra_untrusted: dict[str, float] | None = None,
                 extra_mixed: dict[str, float] | None = None):
        self._trusted   = {**TRUSTED_SOURCES,   **(extra_trusted   or {})}
        self._untrusted = {**UNTRUSTED_SOURCES,  **(extra_untrusted or {})}
        self._mixed     = {**MIXED_SOURCES,      **(extra_mixed     or {})}

    # ── public API ────────────────────────────────────────────────────────────

    def rate_url(self, url: str) -> SourceRating:
        """Rates a single URL. Used to annotate individual search results
        with their credibility tier before judgement (Faza E1)."""
        domain = self._extract_domain(url)
        return self._rate_domain(domain, url, 1)

    def score_results(self, results: list[SearchResult]) -> TruthScore:
        """Main entry point. Accepts the list of SearchResult objects produced
        by the Serper pipeline and returns a TruthScore."""
        if not results:
            return TruthScore(
                score=None,
                label="Fără surse",
                confidence="inconclusive",
                warning="Nu au fost găsite surse de analizat.",
            )

        # Deduplicate by domain, tracking occurrence counts
        domain_map: dict[str, list[str]] = {}   # domain → [url, ...]
        for r in results:
            domain = self._extract_domain(r.source)
            domain_map.setdefault(domain, [])
            if r.source not in domain_map[domain]:
                domain_map[domain].append(r.source)

        # Rate each unique domain
        ratings: list[SourceRating] = []
        for domain, urls in domain_map.items():
            rating = self._rate_domain(domain, urls[0], len(urls))
            ratings.append(rating)

        # Sort: trusted first, then mixed, unknown, untrusted
        tier_order = {
            SourceTier.TRUSTED: 0,
            SourceTier.MIXED: 1,
            SourceTier.UNKNOWN: 2,
            SourceTier.UNTRUSTED: 3,
        }
        ratings.sort(key=lambda r: (tier_order[r.tier], -(r.score or 0)))

        return self._compute_composite(ratings)

    # ── domain rating ─────────────────────────────────────────────────────────

    def _rate_domain(self, domain: str, url: str, occurrences: int) -> SourceRating:
        """Classify a single domain into a tier and assign a score."""

        # Layer 1 — curated trusted list
        if domain in self._trusted:
            score = self._trusted[domain]
            return SourceRating(
                url=url, domain=domain,
                tier=SourceTier.TRUSTED,
                score=score,
                reason=f"Sursă recunoscută cu scor {score}/100 din lista de surse de încredere.",
                occurrences=occurrences,
            )

        # Layer 2 — curated untrusted list
        if domain in self._untrusted:
            score = self._untrusted[domain]
            return SourceRating(
                url=url, domain=domain,
                tier=SourceTier.UNTRUSTED,
                score=score,
                reason=f"Sursă cu credibilitate scăzută, scor {score}/100 din lista neagră.",
                occurrences=occurrences,
            )

        # Layer 3 — curated mixed list
        if domain in self._mixed:
            score = self._mixed[domain]
            return SourceRating(
                url=url, domain=domain,
                tier=SourceTier.MIXED,
                score=score,
                reason=f"Sursă cu credibilitate mixtă, scor {score}/100.",
                occurrences=occurrences,
            )

        # Layer 4 — heuristic for unknown domains
        heuristic_score, reason = self._heuristic_score(domain)
        return SourceRating(
            url=url, domain=domain,
            tier=SourceTier.UNKNOWN,
            score=heuristic_score,
            reason=reason,
            occurrences=occurrences,
        )

    def _heuristic_score(self, domain: str) -> tuple[Optional[float], str]:
        """Estimate trustworthiness from structural domain properties."""
        reasons = []
        score = 50.0  # neutral baseline

        tld = "." + domain.rsplit(".", 1)[-1] if "." in domain else ""

        if tld in _CREDIBLE_TLDS:
            score += 25
            reasons.append(f"TLD oficial/guvernamental ({tld})")
        elif tld in _SUSPICIOUS_TLDS:
            score -= 25
            reasons.append(f"TLD suspect ({tld})")

        # Subdomains of known-good domains
        for trusted_domain in self._trusted:
            if domain.endswith("." + trusted_domain):
                parent_score = self._trusted[trusted_domain]
                score = parent_score * 0.85        # slight discount for sub
                reasons.append(f"Subdomeniu al sursei de încredere {trusted_domain}")
                break

        # Subdomain of untrusted parent
        for bad_domain in self._untrusted:
            if domain.endswith("." + bad_domain):
                score = self._untrusted[bad_domain] * 0.9
                reasons.append(f"Subdomeniu al sursei neacreditate {bad_domain}")
                break

        score = max(0.0, min(100.0, score))
        label = (
            "Domeniu necunoscut, scor euristic calculat pe baza structurii URL-ului."
            if not reasons else
            "Domeniu necunoscut. " + " | ".join(reasons) + "."
        )
        return score, label

    # ── composite score ───────────────────────────────────────────────────────

    def _compute_composite(self, ratings: list[SourceRating]) -> TruthScore:
        """Aggregate individual ratings into one TruthScore."""
        trusted_ratings   = [r for r in ratings if r.tier == SourceTier.TRUSTED]
        mixed_ratings     = [r for r in ratings if r.tier == SourceTier.MIXED]
        untrusted_ratings = [r for r in ratings if r.tier == SourceTier.UNTRUSTED]
        unknown_ratings   = [r for r in ratings if r.tier == SourceTier.UNKNOWN]

        scoreable = trusted_ratings + mixed_ratings + untrusted_ratings

        # If ALL sources are unknown → inconclusive
        if not scoreable:
            return TruthScore(
                score=None,
                label="Neconcludent",
                confidence="inconclusive",
                unknown_count=len(unknown_ratings),
                source_ratings=ratings,
                warning="Toate sursele sunt necunoscute. Scorul nu poate fi calculat.",
            )

        # Weighted average: weight = score_value × occurrences
        weighted_sum   = sum(r.score * r.occurrences for r in scoreable)
        total_weight   = sum(r.occurrences for r in scoreable)
        base_score     = weighted_sum / total_weight

        # Penalty: proportion of untrusted among known sources
        n_known = len(scoreable)
        untrusted_ratio = len(untrusted_ratings) / n_known
        penalty = untrusted_ratio * 30          # up to -30 pts

        # Discount: unknown sources drag score toward center
        unknown_ratio  = len(unknown_ratings) / len(ratings)
        uncertainty_pull = (50.0 - base_score) * unknown_ratio * 0.3

        final_score = max(0.0, min(100.0, base_score - penalty + uncertainty_pull))

        # Confidence level
        if unknown_ratio > 0.6:
            confidence = "low"
        elif unknown_ratio > 0.3 or len(mixed_ratings) > len(trusted_ratings):
            confidence = "medium"
        else:
            confidence = "high"

        # Human-readable label (Romanian)
        if final_score >= 80:
            label = "Surse de înaltă credibilitate"
        elif final_score >= 60:
            label = "Surse de credibilitate medie-ridicată"
        elif final_score >= 40:
            label = "Surse de credibilitate medie"
        elif final_score >= 20:
            label = "Surse de credibilitate scăzută"
        else:
            label = "Surse foarte puțin credibile"

        # Warnings
        warning = None
        unique_domains = {r.domain for r in ratings}
        if len(unique_domains) == 1:
            warning = "Toate sursele provin dintr-un singur domeniu (posibil efect de cameră de ecou)."
        elif untrusted_ratings:
            names = ", ".join(r.domain for r in untrusted_ratings)
            warning = f"Atenție: surse cu credibilitate scăzută detectate: {names}."
        elif unknown_ratio > 0.5:
            warning = (
                f"{len(unknown_ratings)} din {len(ratings)} surse sunt necunoscute. "
                "Scorul poate fi imprecis."
            )

        return TruthScore(
            score=final_score,
            label=label,
            confidence=confidence,
            trusted_count=len(trusted_ratings),
            mixed_count=len(mixed_ratings),
            untrusted_count=len(untrusted_ratings),
            unknown_count=len(unknown_ratings),
            source_ratings=ratings,
            warning=warning,
        )

    # ── utility ───────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Strip scheme, port, path and www. prefix from a URL."""
        try:
            netloc = urlparse(url).netloc or url
        except Exception:
            netloc = url
        # Remove port
        netloc = netloc.split(":")[0]
        # Remove www. prefix only (preserve subdomains like pubmed.ncbi.nlm.nih.gov)
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc.lower()
