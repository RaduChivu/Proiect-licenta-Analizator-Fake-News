# Analizator Fake News — Proiect de licență / Bachelor's Thesis Project

🇷🇴 [Română](#-română) | 🇬🇧 [English](#-english)

---

## 🇷🇴 Română

### Descriere
Sistem automat de verificare a faptelor, bazat pe dovezi, pentru limba română. Primește o afirmație în limbaj natural și returnează un verdict structurat — **CONFIRMAT**, **INFIRMAT** sau **INSUFICIENT VERIFICAT** — înscărcinat de o justificare argumentată și de surse trasabile.

### Arhitectură (lanț de prelucrare cu 4 module)
1. **Regăsirea dovezilor** — descompune afirmația în interogări țintite și adună dovezi web prin Serper API.
2. **SourceRanker** — clasifică domeniile-sursă pe patru niveluri de credibilitate, calibrate pe peisajul media românesc, și calculează un scor compozit (TruthScore).
3. **LLMVerifier** — asamblează afirmația, dovezile și scorul de credibilitate într-un prompt structurat și generează verdictul cu justificare.
4. **Strat API (FastAPI)** — validează ieșirea (Pydantic), expune endpoint-ul `POST /check` și servește o interfață web HTML cu redare progresivă prin Server-Sent Events.

### Evaluare
Set de test propriu, adnotat manual: 90 de afirmații (15 CONFIRMAT, 45 INFIRMAT, 30 INSUFICIENT VERIFICAT). Acuratețe globală: 52,2%; macro F1: 0,50.

### Lucrarea de licență
Textul complet al lucrării (Radu Chivu) va fi adăugat în acest repository, în folderul `docs/`.

### Stare
Repository inițial. Codul sursa va fi adăugat ulterior.

---

## 🇬🇧 English

### Description
An evidence-based automated fact-checking system for the Romanian language. It takes a natural-language claim and returns a structured verdict — **CONFIRMED**, **REFUTED**, or **INSUFFICIENTLY VERIFIED** — backed by a reasoned justification and traceable sources.

### Architecture (4-module pipeline)
1. **Evidence retrieval** — decomposes the claim into targeted queries and gathers web evidence via the Serper API.
2. **SourceRanker** — classifies source domains into four reliability tiers calibrated to the Romanian media landscape and computes a composite credibility score (TruthScore).
3. **LLMVerifier** — assembles the claim, evidence, and credibility signal into a structured prompt and generates the verdict with justification.
4. **API layer (FastAPI)** — validates output (Pydantic), exposes a `POST /check` endpoint, and serves a lightweight HTML web UI with progressive rendering via Server-Sent Events.

### Evaluation
Custom manually annotated test set: 90 claims (15 CONFIRMED, 45 REFUTED, 30 INSUFFICIENTLY VERIFIED). Overall accuracy: 52.2%; macro F1: 0.50.

### Bachelor's thesis
The full thesis text (Radu Chivu) will be added to this repository under the `docs/` folder.

### Status
Initial repository. Source code will be added later.
