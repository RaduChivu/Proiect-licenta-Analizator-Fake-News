# schemas.py
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional


class Source(BaseModel):
    """O sursă de informație utilizată în verificarea faptelor."""

    url: str = Field(
        ...,
        description="URL-ul complet al sursei",
        examples=["https://digi24.ro/articol-exemplu"]
    )
    question: Optional[str] = Field(
        None,
        description="Întrebarea de verificare asociată cu această sursă",
        max_length=500
    )
    domain: Optional[str] = Field(
        None,
        description="Domeniul sursei (ex: digi24.ro)",
        examples=["digi24.ro", "wikipedia.org"]
    )
    tier: Optional[str] = Field(
        None,
        description="Nivelul de incredere al sursei: trusted | mixed | untrusted | unknown"
    )
    trust_score: Optional[float] = Field(
        None,
        description="Scorul de credibilitate al domeniului sursei (0-100)",
        ge=0.0,
        le=100.0
    )
    title: Optional[str] = Field(
        None,
        description="Titlul paginii web",
    )
    snippet: Optional[str] = Field(
        None,
        description="Fragmentul relevant din pagina web",
    )
    reason: Optional[str] = Field(
        None,
        description="Motivul clasificării sursei (de ce are acest tier)",
    )

    @field_validator("url")
    @classmethod
    def url_must_be_valid(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            v = "https://" + v
        return v.rstrip("/")


class FactCheckRequest(BaseModel):
    """Cerere de verificare a unei afirmații."""

    content: str = Field(
        ...,
        description="Afirmația care trebuie verificată",
        min_length=5,
        max_length=1000,
        examples=["România a câștigat Cupa Mondială în 2022"]
    )
    language: Optional[str] = Field(
        default="ro",
        description="Limba afirmației (momentan doar 'ro' suportat)",
        pattern="^(ro|en)$"
    )


class SourceRatingSchema(BaseModel):
    """Evaluarea unei singure surse."""
    url: str
    domain: str
    tier: str = Field(..., description="trusted | mixed | untrusted | unknown")
    score: Optional[float] = Field(None, ge=0.0, le=100.0)
    reason: str
    occurrences: int = 1


class TruthScoreSchema(BaseModel):
    """Scorul compozit de credibilitate al tuturor surselor.

    Expune doar scorul agregat, eticheta și metadate de nivel înalt.
    Lista detaliată de surse este disponibilă intern prin ``to_dict_full()``.
    """
    score: Optional[float] = Field(
        None, ge=0.0, le=100.0,
        description="Scorul agregat de credibilitate (0-100). None = neconcludent."
    )
    label: str = Field(
        ...,
        description="Etichetă lizibilă în română (ex: 'Surse credibile')."
    )
    confidence: str = Field(
        ...,
        description="Nivelul de certitudine al scorului: high | medium | low | inconclusive"
    )
    source_count: int = Field(
        0,
        description="Numărul total de domenii unice analizate."
    )
    warning: Optional[str] = Field(
        None,
        description="Avertisment opțional (ex: surse dintr-un singur domeniu, surse neacreditate)."
    )


class FactCheckResponse(BaseModel):
    """Răspuns structurat pentru verificarea faptelor."""

    claim: str = Field(
        ...,
        description="Afirmația verificată (exact cum a fost trimisă)",
        examples=["România a câștigat Cupa Mondială în 2022"]
    )
    verdict: str = Field(
        ...,
        description="Verdictul final: CONFIRMAT, INFIRMAT, sau INSUFICIENT VERIFICAT",
    )
    justification: str = Field(
        ...,
        description="Raționamentul detaliat al sistemului pentru verdict",
    )
    sources: List[Source] = Field(
        default_factory=list,
        description="Lista surselor utilizate în procesul de verificare",
        max_length=20
    )
    confidence: Optional[float] = Field(
        None,
        description="Nivelul de încredere al sistemului (0.0 - 1.0)",
        ge=0.0,
        le=1.0
    )
    claim_id: Optional[int] = Field(
        None,
        description="ID-ul intern al claim-ului pentru tracking"
    )
    truth_score: Optional[TruthScoreSchema] = Field(
        None,
        description="Scorul de credibilitate al surselor de evidență"
    )


class ErrorResponse(BaseModel):
    """Răspuns pentru erori API."""

    error: str = Field(..., description="Tipul erorii")
    message: str = Field(..., description="Mesajul de eroare detaliat")
    details: Optional[dict] = Field(None, description="Informații suplimentare despre eroare")
