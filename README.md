# Enterprise AI Incident Resolution & Knowledge Copilot

> **Status: Phase 1 of 15 — architecture & repo scaffolding.**
> This README grows with each phase; see `docs/PHASES.md` (added later) for the full build log.

A production-oriented, multi-agent AI system that helps enterprise IT/support
teams diagnose and resolve technical incidents by combining:

- **Retrieval-Augmented Generation (RAG)** over enterprise SOPs/runbooks (hybrid vector + BM25 + reranking)
- **SQL agent** over a structured incident/ticket database
- **Tool-calling agents** for live system/device checks and ticket management
- **LangGraph orchestration** across a router → RAG/SQL/tools → diagnosis → validation → (safe response | human review) pipeline
- **Guardrails and human-in-the-loop approval** for risky actions
- **Evaluation and observability** with real, measured (never fabricated) metrics

## Why this exists

Enterprise IT teams handle repetitive incidents (VPN errors, auth failures,
software regressions after updates) that already have documented solutions
and historical precedent scattered across SOPs, wikis, and ticket systems.
This project builds a copilot that *actually reasons across all three* —
documentation, structured history, and live system state — before proposing
an action, and refuses to act autonomously on anything risky.

## Two run modes, one codebase

| | `APP_ENV=local` (default, offline, no keys) | `APP_ENV=production` |
|---|---|---|
| LLM | deterministic offline "dummy" provider | OpenAI / Anthropic (pluggable) |
| Embeddings | offline hashing embedder | OpenAI / sentence-transformers |
| Database | SQLite (`data/local.db`) | PostgreSQL |
| Vector store | FAISS (local file index) | Qdrant |

All of this is controlled by `.env` (copy `.env.example`) and `app/config.py`
— no code branches on environment elsewhere.

## Architecture

```
                         ┌──────────────────────┐
                         │       USER            │
                         └──────────┬────────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ ORCHESTRATOR / ROUTER │
                         └──────────┬────────────┘
                                    │
                 ┌──────────────────┼──────────────────┐
                 ▼                  ▼                  ▼
          ┌────────────┐     ┌────────────┐    ┌────────────┐
          │ RAG AGENT  │     │ SQL AGENT  │    │ TOOL AGENT │
          └──────┬─────┘     └──────┬─────┘    └──────┬─────┘
                 └──────────────────┼──────────────────┘
                                    ▼
                         ┌──────────────────────┐
                         │  DIAGNOSIS AGENT      │
                         └──────────┬────────────┘
                                    ▼
                         ┌──────────────────────┐
                         │ VALIDATION AGENT      │
                         └──────────┬────────────┘
                     ┌──────────────┴──────────────┐
                     ▼                              ▼
             ┌───────────────┐             ┌───────────────┐
             │ SAFE RESPONSE │             │ HUMAN REVIEW  │
             └───────────────┘             └───────────────┘
```

(Full component-level architecture, RAG pipeline diagram, and DB schema are
added in Phases 3–4 as those subsystems land.)

## Project structure

```
enterprise-ai-incident-copilot/
├── app/
│   ├── agents/        # orchestrator, rag, sql, tool, diagnosis, validation agents
│   ├── graph/          # LangGraph state + workflow
│   ├── rag/            # ingestion, chunking, embeddings, retrieval, reranking, citations
│   ├── tools/          # typed tool implementations
│   ├── guardrails/     # input/output/security guardrails
│   ├── evaluation/     # eval datasets + retrieval/generation metric runners
│   ├── monitoring/     # logging, metrics, tracing
│   ├── api/            # FastAPI routes + schemas
│   ├── database/       # SQLAlchemy models, session, seed data
│   ├── config.py        # single source of truth for env-driven settings
│   └── main.py          # FastAPI entrypoint
├── frontend/            # Streamlit app
├── data/                # synthetic documents, incidents, evaluation sets
├── scripts/
├── tests/
├── .github/workflows/   # CI
├── Dockerfile, docker-compose.yml
├── requirements.txt / pyproject.toml
├── .env.example
└── README.md
```

## Database design (Phase 2)

13 tables under `app/database/models.py`, split into three groups:

- **Core entities**: `users`, `devices`, `software_versions`, `system_status`,
  `incidents`, `incident_history`, `tickets`
- **Knowledge base**: `documents`, `document_metadata` — registers the 15
  synthetic SOPs/guides/policies/reference docs under `data/documents/` with
  department, version, and access-level metadata for RAG filtering
- **Agentic/observability**: `agent_runs`, `tool_calls`, `evaluations`,
  `human_approvals` — populated in later phases as the LangGraph pipeline runs

Seed data (`app/database/seed.py`, deterministic — fixed seed 42):

- 60 users across 8 departments, 1–2 devices each (Windows/macOS/Linux mix)
- 150 incidents across 5 categories (VPN, Authentication, Network, Endpoint
  Security, Software) with realistic error codes, severities, and resolutions
- A deliberately-seeded known-bad version pairing (CorpVPN Client 4.12.1 +
  Windows 24H2 → VPN Error 691) that is referenced consistently across both
  the structured data *and* the synthetic documents below, so the RAG agent
  (Phase 3) and SQL agent (Phase 4) can be evaluated on whether they actually
  cross-reference the two sources correctly.

Seed the local database:

```bash
python -m app.database.seed          # seed if empty
python -m app.database.seed --reset   # drop + reseed
```

## Synthetic knowledge base (Phase 2)

15 original documents in `data/documents/` (SOPs, guides, policies,
reference tables, release notes) covering VPN, authentication, MFA,
network, endpoint security, and IT service management — all fabricated,
not copied from any real vendor/enterprise documentation. Each carries
YAML frontmatter (`document_type`, `department`, `version`,
`access_level`) that the RAG ingestion pipeline (Phase 3) will parse into
chunk metadata for filtering.

## RAG pipeline (Phase 3)

```
Documents (data/documents/*.md)
    ↓ ingestion.py       — parse frontmatter, clean text
    ↓ chunking.py         — section-aware split + sliding-window overlap
    ↓ embeddings.py        — dummy hashing embedder (offline) / OpenAI / sentence-transformers
    ↓ vector_store.py      — FAISS (local, numpy fallback) / Qdrant (production)
    ↓ retrieval.py          — BM25 + vector search fused via reciprocal rank fusion, metadata filtering
    ↓ reranking.py           — lexical query-coverage reranker (swappable for a cross-encoder)
    ↓ citations.py            — numbered context blocks + structured citation list, access-level filtered
    ↓ llm/provider.py          — dummy extractive / OpenAI / Anthropic, swappable via LLM_PROVIDER
    ↓ pipeline.py               — RAGPipeline.build() + .answer()
```

Every retrieved chunk carries: `document_id`, `document_name`,
`document_type`, `department`, `version`, `section`, `created_at`,
`access_level` — enabling metadata filtering (e.g. "only Security
department documents") before fusion and citation-level access
enforcement as defense in depth.

The **dummy LLM provider** (`LLM_PROVIDER=dummy`, the local-mode default)
is not a stub — it performs deterministic extractive synthesis (keyword-
overlap sentence ranking over retrieved context), so the full pipeline is
genuinely exercisable and testable offline. Verified against the project's
sample query end-to-end in this environment: asking about "VPN error 691
after a Windows update" correctly retrieves and synthesizes the
known-bad-version-pairing explanation (CorpVPN Client 4.12.1 + Windows
24H2) from three different documents.

Build the index and run a smoke query:

```bash
python scripts/build_rag_index.py
```

## Getting started (local mode — no API keys needed)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # defaults already run fully offline
uvicorn app.main:app --reload
# in another terminal:
curl http://localhost:8000/health
```

Run tests:

```bash
pytest
ruff check .
mypy app
```

## Roadmap (build phases)

- [x] Phase 1 — Architecture, repo scaffolding, config abstraction, health check
- [x] Phase 2 — Synthetic enterprise dataset (13-table schema + 15 SOP/guide/policy documents + deterministic seed generator)
- [x] Phase 3 — Hybrid RAG pipeline (ingestion, chunking, embeddings, FAISS/Qdrant, BM25, hybrid fusion, reranking, citations, swappable LLM)
- [ ] Phase 4 — SQL + incident tools
- [ ] Phase 5 — LangGraph orchestration
- [ ] Phase 6 — Diagnosis + validation agents
- [ ] Phase 7 — Guardrails + human approval
- [ ] Phase 8 — FastAPI (full route set)
- [ ] Phase 9 — Streamlit UI
- [ ] Phase 10 — Evaluation framework
- [ ] Phase 11 — Observability
- [ ] Phase 12 — Docker
- [ ] Phase 13 — Testing (unit/integration/adversarial)
- [ ] Phase 14 — CI/CD
- [ ] Phase 15 — Final docs + interview prep materials

## Security

- Secrets never committed — see `.gitignore` and `.env.example`
- SQL agent restricted to read-only, validated queries (Phase 4)
- Guardrails against prompt injection, jailbreaks, and data exfiltration (Phase 7)
- High-risk actions always require human approval (Phase 7)

## License

MIT — see `LICENSE`.
