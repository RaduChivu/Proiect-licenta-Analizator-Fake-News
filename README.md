# Analizator Fake News — Proiect de licență / Bachelor's Thesis Project

🇷🇴 [Română](#-română) | 🇬🇧 [English](#-english)

---

## 🇷🇴 Română

### Descriere
Sistem automat de verificare a faptelor pentru limba română. Primește o afirmație și returnează un verdict (**CONFIRMAT**, **INFIRMAT** sau **INSUFICIENT VERIFICAT**), o justificare și sursele folosite, fiecare cu un nivel de credibilitate (`trusted`, `mixed`, `untrusted`, `unknown`) și un scor global (TruthScore).

Pipeline-ul folosește căutare web prin Serper (Google, scopat pe România) și Wikipedia în română, un model de limbaj **local** (`google/gemma-3-4b-it`, rulat prin Hugging Face Transformers) și un modul `SourceRanker` pentru credibilitatea surselor. Aplicația este expusă printr-un API **FastAPI**, cu interfață web proprie și compatibilitate OpenAI pentru Open WebUI.

### Cerințe
- Python 3.10+ și Git
- Cont Hugging Face cu un token de acces și acces acceptat la modelul [google/gemma-3-4b-it](https://huggingface.co/google/gemma-3-4b-it)
- Cheie API Serper (https://serper.dev)
- Spațiu pe disc și memorie suficientă pentru modelul local (la prima rulare se descarcă automat)

### Instalare
```bash
git clone https://github.com/RaduChivu/Proiect-licenta-Analizator-Fake-News.git
cd Proiect-licenta-Analizator-Fake-News

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
pip install fastapi uvicorn      # dacă nu sunt deja instalate
python -c "import nltk; nltk.download('wordnet')"
```

### Configurare chei API
Creează fișierul `config/api_keys.yaml` (este ignorat de Git, nu îl urca pe GitHub):
```yaml
huggingface_user_access_token: "hf_..."
serper_api_key: "..."
openai_api_key: ""
```

### Pornire
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```
Deschide http://localhost:8000 pentru interfața web. Documentația interactivă a API-ului este la http://localhost:8000/docs. La prima verificare, modelul este încărcat în memorie, deci prima cerere durează mai mult.

Pe Mac cu Apple Silicon, codul folosește automat acceleratorul MPS; pe sisteme cu NVIDIA, CUDA.

### Endpoint-uri API
| Metodă | Cale | Rol |
|---|---|---|
| GET | `/` | Interfața web |
| GET | `/health` | Verificare stare |
| POST | `/chat` (alias `/ro/chat`) | Verificare, răspuns JSON complet |
| POST | `/chat/stream` | Verificare cu progres în timp real (SSE) |
| POST | `/v1/chat/completions` | Format compatibil OpenAI (pentru Open WebUI) |
| GET | `/v1/models` | Lista modelelor (`infact-ro`) |
| GET | `/history?limit=20` | Ultimele verificări |

Exemplu:
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Bucureștiul este capitala României."}]}'
```

### Open WebUI (opțional)
În Open WebUI adaugă o conexiune OpenAI cu URL-ul `http://localhost:8000/v1` și orice cheie (de exemplu `dummy`). Alternativ, `docker compose up --build` pornește API-ul pe portul 8000 și Open WebUI pe portul 3000. Docker de obicei nu folosește accelerarea GPU de pe Mac, deci modelul local va fi lent în container.

### Istoric și fișiere generate
Rezultatele se salvează în folderul `out/` (istoric SQLite în `out/history.db`, documente și surse pe verificare).

### Lucrarea de licență
Textul complet al lucrării este în fișierul `RaduChivu_Final.docx`.

### Atribuire
Proiectul pornește de la [InFact](https://github.com/multimodal-ai-lab/DEFAME) (TU Darmstadt, licență Apache 2.0), adaptat pentru limba română, cu SourceRanker, interfață FastAPI și integrare Open WebUI.

---

## 🇬🇧 English

### Description
An automated fact-checking system for the Romanian language. It takes a claim and returns a verdict (**CONFIRMED**, **REFUTED**, or **INSUFFICIENTLY VERIFIED**; the API returns the Romanian labels), a justification, and the sources used, each with a credibility tier (`trusted`, `mixed`, `untrusted`, `unknown`) and an overall TruthScore.

The pipeline uses web search through Serper (Google, scoped to Romania) and Romanian Wikipedia, a **local** language model (`google/gemma-3-4b-it`, run with Hugging Face Transformers), and a `SourceRanker` module for source credibility. It is exposed through a **FastAPI** service with its own web UI and OpenAI-compatible endpoints for Open WebUI.

### Requirements
- Python 3.10+ and Git
- A Hugging Face account with an access token and accepted access to [google/gemma-3-4b-it](https://huggingface.co/google/gemma-3-4b-it)
- A Serper API key (https://serper.dev)
- Enough disk space and memory for the local model (downloaded automatically on first run)

### Installation
```bash
git clone https://github.com/RaduChivu/Proiect-licenta-Analizator-Fake-News.git
cd Proiect-licenta-Analizator-Fake-News

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
pip install fastapi uvicorn      # if not already installed
python -c "import nltk; nltk.download('wordnet')"
```

### API key configuration
Create `config/api_keys.yaml` (it is git-ignored, never commit it):
```yaml
huggingface_user_access_token: "hf_..."
serper_api_key: "..."
openai_api_key: ""
```

### Run
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```
Open http://localhost:8000 for the web UI. Interactive API docs are at http://localhost:8000/docs. The model is loaded on the first check, so the first request is slower.

On Apple Silicon the code uses the MPS accelerator automatically; on NVIDIA systems it uses CUDA.

### API endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Web UI |
| GET | `/health` | Health check |
| POST | `/chat` (alias `/ro/chat`) | Fact-check, full JSON response |
| POST | `/chat/stream` | Fact-check with live progress (SSE) |
| POST | `/v1/chat/completions` | OpenAI-compatible (for Open WebUI) |
| GET | `/v1/models` | Model list (`infact-ro`) |
| GET | `/history?limit=20` | Latest checks |

Example:
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Bucureștiul este capitala României."}]}'
```

### Open WebUI (optional)
In Open WebUI, add an OpenAI connection with the URL `http://localhost:8000/v1` and any key (for example `dummy`). Alternatively, `docker compose up --build` starts the API on port 8000 and Open WebUI on port 3000. Docker usually cannot use Apple GPU acceleration on a Mac, so the local model will be slow inside a container.

### History and generated files
Results are stored in `out/` (SQLite history in `out/history.db`, plus per-check documents and sources).

### Bachelor's thesis
The full thesis text is in `RaduChivu_Final.docx`.

### Attribution
This project builds on [InFact](https://github.com/multimodal-ai-lab/DEFAME) (TU Darmstadt, Apache 2.0 license), adapted for Romanian with SourceRanker, a FastAPI interface, and Open WebUI integration.
