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
- [ ] Phase 2 — Synthetic enterprise dataset (documents + DB)
- [ ] Phase 3 — Hybrid RAG pipeline
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
