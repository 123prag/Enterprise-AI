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

## SQL agent & tools (Phase 4)

**SQL safety model**: the primary path (`app/agents/sql_agent.py`
`SQLAgent`) never builds SQL by string interpolation — every query is a
SQLAlchemy expression with bound parameters, so it is not injectable by
construction. A separate `execute_readonly_sql()` path exists for any
future free-form/LLM-generated SQL and is gated by `validate_readonly_sql()`,
which rejects anything that isn't a single `SELECT` against a whitelisted
table, with no forbidden keywords (`insert`/`update`/`delete`/`drop`/
`alter`/`;`/`--`/etc). Verified directly against 8 attack patterns
(DROP, DELETE, UPDATE, stacked statements, INSERT, non-whitelisted table,
empty input) — all correctly rejected — plus one legitimate parameterized
SELECT, correctly accepted.

**Tools** (`app/tools/`), each with typed Pydantic input/output,
validation, error handling, and logging:

| Tool | Purpose |
|---|---|
| `search_knowledge_base` | RAG pipeline query with department/type filtering |
| `search_incidents` | Structured, parameterized incident search |
| `get_incident_history` | Audit trail + related-incident lookup for one incident |
| `check_system_status` | Live service status (VPN gateways, SSO, DNS, ...) |
| `check_software_version` | Known-problematic-version lookup |
| `create_ticket` / `update_ticket` / `get_ticket` | Ticket lifecycle, with illegal-transition guards (e.g. `pending_approval` can't jump straight to `resolved`) |
| `calculate_priority` | Deterministic, explainable severity/impact scoring (not an LLM judgment call) |

`app/agents/tool_agent.py` provides one dispatch point (`dispatch(tool_name,
input_dict)`) used by the LangGraph orchestrator (Phase 5) — it validates
input against the tool's schema, runs it, and logs every call's latency/
success/error into the `tool_calls` table for observability.

Priority scoring was verified directly: a low-severity/single-user
incident scores 1.0 ("low"), while a high-severity incident affecting 5+
users on a known-bad software version in a critical department scores
6.0 ("critical").

## Orchestration (Phase 5)

```
START -> router -> {rag, sql, tools}  (fan-out, run concurrently)
                          |
                          v  (fan-in)
                      diagnosis
                          |
                          v
                     validation
                    /     |      \
              valid   invalid,    requires_human
                |      retries       |
                v      left          v
         safe_response  |      human_review
                |        v            |
               END   (loop to     END
                     diagnosis)
```

**Router** (`app/agents/orchestrator.py`) is a deliberately transparent,
rule-based classifier — not an LLM call — since routing decisions gate
which agents run and whether an action requires human approval, and
those need to be deterministic and auditable. It was verified against
every sample query in the spec, including the one hard requirement:
`"Change the production VPN configuration."` correctly sets
`requires_human=True` and `priority=critical`.

**Graph shape** is implemented twice from the same node functions
(`app/graph/nodes.py`), so it's genuinely testable in this environment
without the `langgraph` package installed:
- `app/graph/runner.py` — a dependency-free sequential executor with
  identical semantics (fan-out/fan-in, retry loop bounded by
  `MAX_AGENT_RETRIES`, immediate escalation for high-risk actions)
- `app/graph/workflow.py` — the real `langgraph.graph.StateGraph` wiring
  for production, where RAG/SQL/tools genuinely execute concurrently

Both consume the same `GraphDeps` dependency-injection point
(`app/graph/deps.py`), so tests use fakes while production wires to the
real `tool_agent.dispatch`.

**Diagnosis and validation are placeholders in this phase** (heuristic
confidence scoring, evidence-presence checks) — Phase 6 replaces them
with dedicated agents that reason more carefully over the gathered
evidence. The graph *shape*, retry bound, and escalation rule are final.

Verified end-to-end in this sandbox across 3 scenarios: strong evidence
→ safe response (confidence 0.90); no evidence → 3 retries → human
escalation; high-risk action → immediate escalation with the risky tool
action correctly **blocked from execution**, not merely flagged.

## Diagnosis & validation agents (Phase 6)

**Diagnosis** (`app/agents/diagnosis_agent.py`) combines RAG citations,
the RAG pipeline's own synthesized answer, historical incidents, and a
live cross-reference against `check_software_version` into one
structured output. Confidence is **deterministic and evidence-driven**,
not a model's self-reported certainty — it's built additively from what
was actually found:

| Signal | Confidence contribution |
|---|---|
| (base) | 0.15 |
| RAG citations found | +0.30 |
| Historical incidents found | +0.20 |
| Confirmed known-bad software version | +0.25 |
| Degraded live system status | +0.15 |

`extract_software_signal()` pulls a (product, version) pair from an
explicit mention in the query or the most common version among retrieved
incidents, then the diagnosis node calls the real `check_software_version`
tool (not a hardcoded lookup) to confirm it — this is the mechanism that
lets the graph automatically surface the CorpVPN 4.12.1 / Windows 24H2
regression seeded back in Phase 2.

**Validation** (`app/agents/validation_agent.py`) checks, in order:
1. **Policy compliance** — a high-risk classification always wins,
   regardless of diagnosis confidence (a 0.99-confidence diagnosis is
   still rejected if the request itself was high-risk).
2. **Evidence support** — a diagnosis with zero evidence entries fails.
3. **Citation correctness / hallucination** — every `[n]` marker in the
   diagnosis text must correspond to a real citation; a reference to a
   citation that doesn't exist fails validation by name.
4. **Confidence threshold** — below `DIAGNOSIS_CONFIDENCE_THRESHOLD`
   (default 0.7), human review is required.
5. **Unsafe recommendations** — the diagnosis agent is never allowed to
   recommend direct execution of a high-risk action.

Both agents are pure functions over plain data (no pydantic/SQLAlchemy),
so all **13 of their tests were executed directly with the real Python
interpreter** in this sandbox — no shim needed — covering the zero-
confidence high-risk short-circuit, monotonic confidence growth across
each evidence source, verbatim use of the RAG answer, both signal-
extraction paths, and all 5 validation failure modes above. The full
graph (Phase 5's runner, now wired to these real agents) was re-verified
end-to-end afterward: all 6 scenario tests still pass, including the
known-bad-version case reaching 0.90 confidence.

## Guardrails & human approval (Phase 7)

The graph now has two more nodes, bookending everything from Phase 5/6:

```
START -> guardrail_input --blocked--> guardrail_output -> END
              |
           proceed
              v
           router -> {rag, sql, tools} -> diagnosis -> validation -> ... -> safe_response/human_review -> guardrail_output -> END
```

**Input guardrails** (`app/guardrails/input.py`) pattern-match for prompt
injection/jailbreak attempts, requests for system internals or secrets,
and SQL-injection-shaped strings — a blocked query never reaches the
router at all. **Output guardrails** (`app/guardrails/output.py`) scan
every final response for leaked credentials (API-key/AWS-key shaped
strings, `-----BEGIN ... PRIVATE KEY-----`) and system-prompt echoes,
redacting or withholding the response regardless of how the leak got
there — this is a genuinely independent safety net from Phase 6's
hallucination/citation checks, verified by a test where the diagnosis
pipeline has no reason to flag a leaked-looking string but the output
guardrail catches it anyway.

**Security utilities** (`app/guardrails/security.py`): a real sliding-
window `RateLimiter` (in-memory, swappable for Redis-backed later behind
the same interface) and a minimal bearer-token `AuthContext` abstraction
for the FastAPI layer (Phase 8). The SQL-injection validator from Phase 4
is re-exported here too, lazily (via module `__getattr__`) so that rate
limiting and auth — which need nothing but the standard library — aren't
forced to pull in pydantic/SQLAlchemy just to be imported.

**Human approval** (`app/tools/approvals.py`) is now a real, persisted
workflow against the `human_approvals` table: `request_human_approval`,
`approve_action`, `reject_action`, `request_more_information`,
`get_pending_approvals` — with a guard against re-deciding an
already-decided approval. The graph's `human_review` node calls
`request_human_approval` for real now, instead of just returning an
escalation message, so every escalation is durably recorded for the
Streamlit approval page (Phase 9) to act on.

All of `input.py`, `output.py`, and (after refactoring out its eager
sql_agent import) `security.py`'s `RateLimiter`/`AuthContext` depend on
nothing but the standard library, so **all 16 of their tests ran with
the real, unmodified Python interpreter** in this sandbox — including
every named injection/jailbreak pattern, both secret-pattern types, and
the sliding-window rate limiter's expiry behavior. The full graph was
re-verified afterward (8 scenarios now, up from 6) via the pydantic
shim, including the two new ones: a prompt-injection query correctly
blocked before the router ever runs, and a simulated leaked API key in
a RAG answer correctly redacted from the final response even though it
had high enough confidence to otherwise pass validation cleanly.

## API (Phase 8)

| Method | Path | Purpose |
|---|---|---|
| POST | `/chat` | Runs a query through the full graph (guardrails → router → RAG/SQL/tools → diagnosis → validation → response/escalation) |
| POST | `/incidents` | Create an incident record |
| GET | `/incidents/{incident_ref}` | Incident detail + history + related incidents |
| POST | `/search` | Direct knowledge-base + incident search, bypassing the full agentic pipeline |
| POST | `/approve-action` / `/reject-action` | Human decisions on a pending approval |
| GET | `/health` | Liveness probe |
| GET | `/metrics` | Real counts from `agent_runs`/`tool_calls`/`human_approvals`/`evaluations` — zeros on an empty DB, never fabricated |
| POST | `/evaluate` | Returns `501 Not Implemented` with a clear message pointing to Phase 10, rather than fabricating evaluation results before the framework exists |

`/chat` executes through `app.graph.runner.run_graph` (the dependency-free
runner from Phases 5–7) rather than the LangGraph `StateGraph` directly —
both implement the identical state machine over the identical node
functions, so this is a deployment-portability choice, not a different
pipeline. `app.graph.workflow.build_graph()` remains available for
LangGraph-native deployment/visualization.

Every route validates input via Pydantic (422 on bad payloads), returns
proper status codes (404 unknown incident/approval, 400 invalid approval
decision, 429 rate-limited, 501 not-yet-implemented), and goes through a
bearer-token auth dependency (a no-op in local mode when `API_AUTH_TOKEN`
is unset) plus the Phase 7 `RateLimiter`.

`tests/test_api.py` covers all 8 endpoints end-to-end against a seeded
in-memory database, including the full human-approval round trip via the
API (chat triggers escalation → approve via `/approve-action` → confirm
it can't be re-decided) and a real 429 after exhausting the rate limit.

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
- [x] Phase 4 — SQL agent (safe/parameterized, read-only) + typed tool set (search_incidents, get_incident_history, calculate_priority, check_system_status, check_software_version, create/update/get_ticket, search_knowledge_base) + tool agent dispatcher
- [x] Phase 5 — LangGraph orchestration (router -> parallel RAG/SQL/tools -> diagnosis -> validation -> safe response / retry / human review)
- [x] Phase 6 — Diagnosis + validation agents (evidence-weighted confidence, known-bad-version cross-referencing, hallucination/citation/policy checks)
- [x] Phase 7 — Guardrails (input/output/security) + human approval workflow (request/approve/reject/request-more-info, persisted to `human_approvals`)
- [x] Phase 8 — FastAPI (full route set: /chat, /incidents, /search, /approve-action, /reject-action, /health, /metrics, /evaluate) (full route set)
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
