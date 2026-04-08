# AI Clinical Differential Diagnosis Engine

Graph RAG + LLM-powered clinical decision support system. Patient symptoms, history, vitals, and labs go in — ranked differential diagnoses with an interactive reasoning graph come out.

**Not a diagnostic tool.** Clinical decision support only. Every response includes a mandatory disclaimer.

## Architecture

Seven-layer pipeline with 10 guardrail gates, $0/month deployment:

```
Layer 1 — HTTP/Edge         FastAPI, API key auth, rate limiting, 30s timeout
Layer 2 — Input Gates       Emergency detection (medspaCy), schema validation,
                            medical relevance, prompt injection (3-layer), token budget
Layer 3 — Graph RAG         Vector search (Qdrant + fastembed) → 3-hop graph traversal (Neo4j)
Layer 4 — Context Assembly  Subgraph serialization, versioned prompt templates, 8k token budget
Layer 5 — LLM Reasoning     LiteLLM: Groq → Cerebras → small model fallback chain
Layer 6 — Output Gates      Schema validation, hallucination check, treatment filter,
                            confidence threshold, mandatory disclaimer
Layer 7 — Observability     Langfuse tracing, Prometheus metrics, structlog JSON logging
```

## Stack

| Component | Technology | Cost |
|-----------|-----------|------|
| API | FastAPI + Uvicorn | $0 (Fly.io free) |
| Frontend | React 18 + React Flow + Tailwind | $0 (Vercel free) |
| Graph DB | Neo4j AuraDB Free | $0 |
| Vector DB | Qdrant Cloud Free | $0 |
| LLM | Groq + Cerebras (Llama 3.3 70B) via LiteLLM | $0 |
| Embeddings | fastembed (BAAI/bge-micro-v2) in-process | $0 |
| Clinical NLP | medspaCy (negation/context detection) | $0 |
| Knowledge Graph | PrimeKG clinical subset (~30k nodes, ~200k edges) | $0 |
| Observability | Langfuse free tier (50k traces/mo) | $0 |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- Neo4j AuraDB Free account
- Qdrant Cloud Free account
- Groq API key (free)

### Setup

```bash
# Clone
git clone https://github.com/OthmanMohammad/AI-Clinical-Differential-Diagnosis-Engine.git
cd AI-Clinical-Differential-Diagnosis-Engine

# Backend
cp .env.example .env  # Fill in your keys
pip install -r services/api/requirements.in

# Frontend
cd services/frontend && npm install && cd ../..
```

### Data Ingestion

```bash
# 1. Load PrimeKG subset into Neo4j
python -m services.ingestion.primekg_loader \
  --primekg-path data/primekg.csv \
  --neo4j-password $NEO4J_PASSWORD

# 2. Extract medical terms
python -m services.ingestion.extract_medical_terms \
  --neo4j-password $NEO4J_PASSWORD

# 3. Embed and index in Qdrant
python -m services.ingestion.qdrant_indexer \
  --neo4j-password $NEO4J_PASSWORD \
  --qdrant-url $QDRANT_URL \
  --qdrant-api-key $QDRANT_API_KEY

# 4. Build ICD mapping (for eval)
python -m services.ingestion.build_icd_mapping \
  --mondo-sssom data/mondo_mappings.sssom.tsv \
  --neo4j-password $NEO4J_PASSWORD

# 5. Verify
python -m services.ingestion.verify_ingestion \
  --neo4j-password $NEO4J_PASSWORD
```

### Run

```bash
# Backend
cd services/api
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd services/frontend
npm run dev
```

### Test

```bash
cd services/api
python -m pytest tests/ -v
```

## Project Structure

```
services/
  api/                     # FastAPI backend
    app/
      main.py              # App entry, middleware, lifespan
      config.py            # Pydantic settings
      dependencies.py      # DB clients, auth
      routers/             # HTTP endpoints
      core/                # Pipeline: vector_search, graph_traversal, context_builder, llm_client, graph_rag
      guardrails/          # Emergency detector, input/output validation
      models/              # Pydantic request/response models
      observability/       # Langfuse, Prometheus, structlog
    tests/
  ingestion/               # Data pipeline scripts
  frontend/                # React + TypeScript + React Flow
prompts/                   # Versioned YAML prompt templates
eval/                      # Evaluation pipeline + metrics
monitoring/                # Prometheus + Grafana configs
data/                      # Generated data files (gitignored except synonyms)
```

## Key Design Decisions

**medspaCy for emergency detection** — VA-maintained clinical NLP. Deterministic, auditable, 2ms, no external dependency. The emergency gate must never fail because an API is down.

**LiteLLM for LLM calls** — One interface, automatic fallback, provider swap by changing a string. Groq rate-limits? Cerebras picks up automatically.

**Pure Cypher, no APOC** — AuraDB Free doesn't include APOC. The 3-hop traversal query is the only production path.

**fastembed in-process** — For 1-2 users, no need for an external embedding API. Runs in the Fly VM.

**EntityRuler + synonym dict** — Gives medspaCy something to work with for free-text recognition. Synonym dict maps lay-person language ("burning in my chest") to PrimeKG terms ("chest pain").