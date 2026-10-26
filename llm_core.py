# llm_core.py
from __future__ import annotations

import threading
import logging
from datetime import date
from functools import lru_cache
from urllib.parse import urlparse
from infact.fact_checker import FactChecker
from infact.common.label import Label
from schemas import FactCheckResponse, Source, TruthScoreSchema

logger = logging.getLogger(__name__)

_LUNI_RO = [
    "ianuarie", "februarie", "martie", "aprilie", "mai", "iunie",
    "iulie", "august", "septembrie", "octombrie", "noiembrie", "decembrie",
]


def _data_curenta_ro() -> str:
    """Data curentă formatată în română, ex: '4 iulie 2026'."""
    azi = date.today()
    return f"{azi.day} {_LUNI_RO[azi.month - 1]} {azi.year}"

# ─────────────────────────────────────────────
# Etapa curentă a pipeline-ului (G2 — SSE cu etape reale)
# Un singur slot global: serviciul procesează efectiv o verificare o dată
# (modelul local serializează cererile), deci nu are nevoie de stare per-cerere.
# ─────────────────────────────────────────────
_stage_lock = threading.Lock()
_current_stage: dict = {"stage": "idle", "detail": None}


def _set_stage(stage: str, detail: str | None = None) -> None:
    with _stage_lock:
        _current_stage["stage"] = stage
        _current_stage["detail"] = detail


def get_current_stage() -> dict:
    """Etapa reală curentă, inclusă de main.py în evenimentele SSE de progres."""
    with _stage_lock:
        return dict(_current_stage)


def _instrument_stages(fc: FactChecker) -> None:
    """Împachetează metodele-cheie ale pipeline-ului ca să raporteze etapa reală.

    Se aplică o singură dată, la construirea singleton-ului. Etape emise:
    pregatire → intrebari → (cautare ↔ analiza)* → judecata → justificare → finalizat
    """
    import functools

    def wrap(obj, attr: str, stage: str, detail_from_arg: int | None = None):
        orig = getattr(obj, attr)

        @functools.wraps(orig)
        def wrapper(*args, **kwargs):
            detail = None
            if detail_from_arg is not None and len(args) > detail_from_arg:
                detail = str(args[detail_from_arg])[:120]
            _set_stage(stage, detail)
            return orig(*args, **kwargs)

        setattr(obj, attr, wrapper)

    wrap(fc.procedure, "_pose_questions", "intrebari")
    wrap(fc.actor.tools[0], "search", "cautare", detail_from_arg=0)
    wrap(fc.procedure, "attempt_answer_question", "analiza", detail_from_arg=0)
    wrap(fc.judge, "judge", "judecata")
    wrap(fc.doc_summarizer, "summarize", "justificare")


# ─────────────────────────────────────────────
# Lazy singleton pentru Romanian FactChecker
# Instanțiat o singură dată, la prima cerere
# ─────────────────────────────────────────────
_fc_ro_instance: FactChecker | None = None
_fc_ro_lock = threading.Lock()


@lru_cache(maxsize=1)
def _build_fc_ro(data_azi: str) -> FactChecker:
    """Construiește și returnează instanța FactChecker română (singleton).

    Parametrul ``data_azi`` face parte din cheia de cache: la schimbarea
    zilei, instanța este reconstruită (o singură dată pe zi), astfel încât
    ancorarea temporală din prompturi să rămână corectă pentru servicii
    care rulează neîntrerupt mai multe zile.
    """
    fc = FactChecker(
        llm="gemma3_4b",
        print_log_level="info",  # schimbat din debug → reduce zgomotul în logs
        # ── Definiții de clase cu ponderarea credibilității încorporată (E2) ──
        # Definițiile implicite împingeau spre NEI la orice dezacord între surse;
        # aici codificăm explicit că sursele «trusted» decid.
        class_definitions={
            Label.SUPPORTED: (
                "Dovezile susțin sau implică puternic afirmația. Simpla "
                "plauzibilitate NU este suficientă. Simpla menționare împreună a "
                "entităților NU este confirmare — sursa trebuie să afirme explicit "
                "relația."
            ),
            Label.NEI: (
                "Fact-check-ul nu conține suficiente informații pentru o concluzie. "
                "NU alege această opțiune dacă o sursă „trusted” răspunde direct "
                "afirmației: un dezacord venit exclusiv din surse „untrusted” sau "
                "„unknown” NU înseamnă lipsă de informații."
            ),
            Label.REFUTED: (
                "Dovezile contrazic clar afirmația. Alege această opțiune și atunci "
                "când o sursă „trusted” contrazice afirmația, chiar dacă surse "
                "„untrusted” sau „unknown” o susțin. Simpla absență a dovezilor de "
                "susținere NU este suficientă (argument din ignoranță)."
            ),
        },
        search_engines={
            "google": {"gl": "ro", "hl": "ro"},  # Serper scopat pe România, română
            "wiki_ro": {},                         # Wikipedia în română
        },
        extra_prepare_rules=(
            "Afirmația este scrisă în limba română. "
            "Interpretează afirmația exclusiv în română și formulează toate întrebările de verificare a faptelor în română. "
            "Folosește diacritice românești corecte (ă, â, î, ș, ț) în tot textul. "
            "Nu traduce în engleză — procesează totul în română. "
            # ── Ancorare temporală (îmbunătățirea 3) ──
            f"ATENȚIE: Data de astăzi este {data_azi}. "
            "Dacă afirmația privește o stare de fapt care se poate schimba în timp "
            "(funcții publice, componența unor organizații, recorduri, clasificări științifice), "
            "formulează întrebări care verifică explicit dacă faptul mai este valabil ASTĂZI, "
            "nu doar dacă a fost valabil cândva."
        ),
        extra_plan_rules=(
            "Afirmația este în română. Generează TOATE interogările de căutare exclusiv în limba română. "
            "Folosește cuvinte cheie românești cu diacritice corecte (ă, â, î, ș, ț). "
            "Prioritizează surse românești: domenii .ro, publicații românești, instituții române. "
            "Nu folosi o interogare identică sau similară cu una anterioară. "
            "Nu genera interogări în engleză. "
            # ── Căutare adversarială (îmbunătățirea 1) ──
            "OBLIGATORIU: pe lângă interogările care caută confirmarea afirmației, "
            "generează cel puțin o interogare care caută INFIRMAREA ei — de exemplu: "
            "„mit [subiectul afirmației]”, „este adevărat că [afirmația]”, "
            "„[subiectul afirmației] fals” sau „[subiectul afirmației] adevăr sau mit”. "
            "Multe afirmații false sunt mituri populare repetate pe internet; "
            "paginile care demontează mitul se găsesc doar cu interogări de infirmare. "
            # ── Interogări direcționate spre fact-checkeri (Faza 3.1) ──
            "Include cel puțin o interogare direcționată către site-urile românești "
            "de fact-checking, folosind operatorul site: — de exemplu: "
            "„site:factual.ro OR site:veridica.ro [subiectul afirmației]”. "
            "Aceste site-uri verifică profesionist afirmațiile virale din spațiul românesc. "
            # ── Ancorare temporală (îmbunătățirea 3) ──
            f"Data de astăzi este {data_azi}. Pentru afirmații despre stări de fapt "
            "care se pot schimba în timp, include anul curent în cel puțin o interogare "
            f"(ex.: „membrii UE {date.today().year}”, „cea mai înaltă clădire {date.today().year}”)."
        ),
        extra_judge_rules=(
            "Afirmația este în română. "
            "Scrie ÎNTREGUL raționament, rezumatul și concluzia exclusiv în limba română. "
            "Folosește diacritice românești corecte (ă, â, î, ș, ț). "
            "Verdictul și justificarea trebuie să fie clare, concise și în română. "
            # ── Anti-co-ocurență (C2 / fost 1.1) ──
            "REGULĂ CRITICĂ: simpla menționare împreună a entităților din afirmație "
            "într-o sursă NU constituie confirmare. Sursa trebuie să afirme EXPLICIT "
            "relația enunțată în afirmație. Dacă dovezile doar menționează entitățile "
            "(persoane, locuri, date) fără a susține explicit legătura dintre ele, "
            "verdictul nu poate fi „supported”. "
            # ── Ponderarea credibilității surselor (E1+E2 / fost 4.1–4.2) ──
            "Sursele din dovezi sunt etichetate cu credibilitatea lor în formatul "
            "[tier/scor], de exemplu [trusted/85] sau [unknown/50]: "
            "„trusted” = sursă de încredere verificată, „mixed” = credibilitate mixtă, "
            "„untrusted” = sursă cunoscută pentru dezinformare, „unknown” = necunoscută; "
            "scorul este 0–100. "
            "REGULĂ DE PONDERARE: când dovezile din surse diferite se CONTRAZIC, "
            "dovezile din sursele cu tier „trusted” au prioritate față de cele "
            "„mixed”, „unknown” sau „untrusted”, iar la același tier are prioritate "
            "scorul mai mare. Un dezacord între o sursă „trusted” și una „untrusted” "
            "sau „unknown” NU este un conflict real și NU justifică verdictul "
            "„not enough information”: ignoră sursa necredibilă și decide EXCLUSIV "
            "pe baza sursei „trusted”, ca și cum cealaltă nu ar exista. "
            "Nu cere surse suplimentare când există deja o sursă „trusted” care "
            "răspunde direct la întrebare. "
            "Menționează în justificare credibilitatea sursei decisive. "
            # ── Decizie aritmetică (C4 / fost 1.3) ──
            "Dacă afirmația este decidabilă prin calcul (fracții, procente, unghiuri, "
            "sume, conversii de unități, comparații numerice), efectuează calculul "
            "EXPLICIT, pas cu pas, în raționament și bazează verdictul pe rezultatul "
            "calculului, nu pe intuiție și nu pe formulări aproximative din surse. "
            # ── Ancorare temporală (îmbunătățirea 3) ──
            f"Data de astăzi este {data_azi}. Evaluează afirmația raportat la prezent: "
            "un fapt care a fost adevărat în trecut, dar nu mai este valabil astăzi "
            "(ex. o funcție deținută cândva, o apartenență încheiată, un record depășit, "
            "o clasificare științifică abandonată), trebuie considerat INFIRMAT, "
            "iar justificarea trebuie să precizeze că faptul este perimat. "
            "Acordă atenție vechimii dovezilor: o pagină veche care enunță faptul "
            "la timpul prezent nu dovedește că el mai este valabil astăzi. "
            # ── Data publicării surselor (Faza 3.4) ──
            "Când o dovadă are dată de publicare menționată (ex. „publicat: 12.03.2004” "
            "sau „data publicării: ...”), ia în calcul vechimea ei și, dacă e relevantă "
            "pentru verdict, menționează-o explicit în justificare."
        ),
    )
    _instrument_stages(fc)  # G2: etape reale pentru SSE
    return fc


# ─────────────────────────────────────────────
# Counter thread-safe și PERSISTENT pentru claim ID
# (fără persistență, contorul repornea de la 0 la fiecare restart
#  și fișierele salvate cu save_fc_doc se suprascriau)
# ─────────────────────────────────────────────
from pathlib import Path

_counter_lock = threading.Lock()
_COUNTER_FILE = Path("out/claim_counter.txt")


def _load_claim_counter() -> int:
    try:
        return int(_COUNTER_FILE.read_text().strip())
    except (FileNotFoundError, ValueError, OSError):
        return 0


_claim_counter = _load_claim_counter()


# ─────────────────────────────────────────────
# Istoric persistent al verificărilor (G4) — SQLite
# ─────────────────────────────────────────────
import sqlite3

_HISTORY_DB = Path("out/history.db")


def _history_connect() -> sqlite3.Connection:
    _HISTORY_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_HISTORY_DB)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS history ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " claim_id INTEGER,"
        " claim TEXT NOT NULL,"
        " verdict TEXT NOT NULL,"
        " confidence REAL,"
        " truth_score REAL,"
        " source_count INTEGER,"
        " created_at TEXT NOT NULL)"
    )
    return conn


def _save_history(claim: str, verdict: str, confidence: float | None,
                  truth_score: float | None, source_count: int, claim_id: int) -> None:
    from datetime import datetime, timezone
    try:
        with _history_connect() as conn:
            conn.execute(
                "INSERT INTO history (claim_id, claim, verdict, confidence,"
                " truth_score, source_count, created_at) VALUES (?,?,?,?,?,?,?)",
                (claim_id, claim, verdict, confidence, truth_score, source_count,
                 datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
    except sqlite3.Error as exc:
        logger.warning("Nu s-a putut salva în istoric: %s", exc)


def get_history(limit: int = 20) -> list[dict]:
    """Ultimele N verificări, cele mai recente primele (endpoint /history)."""
    try:
        with _history_connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT claim_id, claim, verdict, confidence, truth_score,"
                " source_count, created_at FROM history"
                " ORDER BY id DESC LIMIT ?", (max(1, min(limit, 200)),)
            ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        logger.warning("Nu s-a putut citi istoricul: %s", exc)
        return []


def _next_claim_id() -> int:
    global _claim_counter
    with _counter_lock:
        _claim_counter += 1
        try:
            _COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = _COUNTER_FILE.with_suffix(".tmp")
            tmp.write_text(str(_claim_counter))
            tmp.replace(_COUNTER_FILE)  # scriere atomică
        except OSError as exc:
            logger.warning("Nu s-a putut persista claim_counter: %s", exc)
        return _claim_counter


# ─────────────────────────────────────────────
# Funcția principală de procesare
# ─────────────────────────────────────────────
def get_response(messages: list, language: str = "ro") -> FactCheckResponse:
    """
    Procesează o cerere de fact-checking în limba română.

    Args:
        messages: Listă de dict-uri cu cheile 'role' și 'content'.
        language:  Parametru păstrat pentru compatibilitate API — actualmente doar 'ro'.
    Returns:
        FactCheckResponse: Obiect Pydantic cu verdict, justificare și surse.
    """
    if not messages:
        raise ValueError("Lista de mesaje este goală.")

    user_input = messages[-1]["content"]
    if not user_input or not user_input.strip():
        raise ValueError("Conținutul mesajului este gol.")

    try:
        _set_stage("pregatire")
        fc = _build_fc_ro(_data_curenta_ro())

        # check_content returnează: (label, [FCDocument], [metas])
        result = fc.check_content(user_input)

        label = result[0]      # e.g. <Label.SUPPORTED: 'supported'>
        doc   = result[1][0]   # primul FCDocument
        metas = result[2]      # lista de dict-uri meta, fiecare cu {"q_and_a": [...]}

    except Exception as exc:
        _set_stage("eroare", str(exc)[:120])
        logger.error("Eroare în check_content: %s", exc, exc_info=True)
        raise RuntimeError(f"Eroarea fact-checker-ului: {exc}") from exc

    # Salvare document
    claim_id = _next_claim_id()

    # Mapare verdict → română (folosim label.name nu label.value)
    verdict_ro_map = {
        "SUPPORTED": "CONFIRMAT",
        "REFUTED": "INFIRMAT",
        "NEI": "INSUFICIENT VERIFICAT",
        "CONFLICTING": "INSUFICIENT VERIFICAT",
        "CHERRY_PICKING": "INSUFICIENT VERIFICAT",
        "REFUSED_TO_ANSWER": "INSUFICIENT VERIFICAT",
        "OUT_OF_CONTEXT": "INSUFICIENT VERIFICAT",
        "MISCAPTIONED": "INFIRMAT",
    }
    verdict_ro = verdict_ro_map.get(label.name, "INSUFICIENT VERIFICAT")

    # ─────────────────────────────────────────────
    # Extrage justificarea din FCDocument
    # ─────────────────────────────────────────────
    justification = doc.justification or "Nu există justificare disponibilă."

    # ─────────────────────────────────────────────
    # Extrage TOATE SearchResult-urile direct din FCDocument
    # și clasifică sursele cu SourceRanker (bypass meta["TruthScore"])
    # ─────────────────────────────────────────────
    from infact.tools.source_ranker import SourceRanker

    all_search_results = doc.search_results

    # Hartă url -> question, pentru a păstra contextul întrebării
    url_to_question: dict[str, str] = {}
    for meta in (metas or []):
        for qa in meta.get("q_and_a", []):
            u = qa.get("url", "").strip()
            q = qa.get("question", "").strip()
            if u and u not in url_to_question:
                url_to_question[u] = q

    # Hartă url -> title/snippet din SearchResult.text ("title: snippet")
    url_to_title: dict[str, str] = {}
    url_to_snippet: dict[str, str] = {}
    for r in all_search_results:
        if r.source not in url_to_title and r.text and r.text != "NONE":
            parts = r.text.split(": ", 1)
            if len(parts) == 2:
                url_to_title[r.source] = parts[0].strip()
                url_to_snippet[r.source] = parts[1].strip()
            else:
                url_to_snippet[r.source] = r.text.strip()

    ranker = SourceRanker()
    truth_score = ranker.score_results(all_search_results)
    full = truth_score.to_dict_full()  # include per-source ratings

    sources: list[Source] = []
    for rating in full.get("sources", [])[:15]:
        url = rating.get("url", "")
        if not url:
            continue
        try:
            sources.append(
                Source(
                    url=url,
                    question=url_to_question.get(url),
                    domain=rating.get("domain", ""),
                    tier=rating.get("tier", "unknown"),
                    trust_score=rating.get("score"),
                    title=url_to_title.get(url),
                    snippet=url_to_snippet.get(url),
                    reason=rating.get("reason"),
                )
            )
        except Exception:
            logger.warning("Sursă ignorată (URL invalid): %s", url)

    # ─────────────────────────────────────────────
    # Construiește TruthScore din meta["TruthScore"]
    # ─────────────────────────────────────────────
    truth_score_schema = TruthScoreSchema(
        score=full.get("score"),
        label=full.get("label", "Necunoscut"),
        confidence=full.get("confidence", "inconclusive"),
        source_count=full.get("source_count", 0),
        warning=full.get("warning"),
    )

    # Salvare document și surse pe disc
    try:
        fc.logger.save_fc_doc(doc, claim_id=claim_id)
        fc.logger.save_sources(
            [s.model_dump() for s in sources],
            claim_id=claim_id,
        )
    except Exception as exc:
        logger.warning("Nu s-a putut salva documentul (claim_id=%d): %s", claim_id, exc)

    # Confidence = average of all source trust_scores (0-1 scale)
    scored = [s.trust_score for s in sources if s.trust_score is not None]
    avg_confidence = (sum(scored) / len(scored) / 100.0) if scored else None

    # Istoric persistent (G4)
    _save_history(
        claim=user_input,
        verdict=verdict_ro,
        confidence=avg_confidence,
        truth_score=truth_score_schema.score,
        source_count=truth_score_schema.source_count,
        claim_id=claim_id,
    )
    _set_stage("finalizat")

    return FactCheckResponse(
        claim=user_input,
        verdict=verdict_ro,
        justification=justification,
        sources=sources,
        confidence=avg_confidence,
        claim_id=claim_id,
        truth_score=truth_score_schema,
    )
