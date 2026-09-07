# Implementation notes and verification record

The earlier review was verified against the local branch. Confirmed problems included regex-only extraction, direct calls to decorated tools, skipped vendor checks, text parsing of tool results, blanket interrupts, unconditional success after writes, and a category-driven benchmark. The local tree was clean before implementation.

## Files and responsibilities

| File | Responsibility |
|---|---|
| `backend/app/config.py`, `.env.example` | Shared environment configuration and bounded execution limits |
| `backend/app/contracts.py`, `gemini.py` | Pydantic contracts, maintained Google Gen AI SDK, bounded structured retries, source validation and native read-only function calls |
| `backend/app/mcp_client.py` | Actual stdio lifecycle, tool discovery, schema validation and private application write capability |
| `mcp_servers/audit_server.py` | Five structured MCP tools; legacy server names forward here |
| `backend/app/policies.py`, `policy_index.py` | One authoritative rule representation, generated versioned documents, Chroma/MiniLM indexing and validation |
| `backend/app/storage.py`, `sql/migrate_v2.sql` | Parameterized SQL Server queries, explicit SQLite demo mode and idempotent confirmed writes |
| `backend/app/web_risk.py` | Bounded Tavily HTTP calls, source metadata, explicit unavailable/demo and identity uncertainty |
| `backend/app/agent/audit_graph.py` | Mandatory checks, optional bounded model tool loop, deterministic routing, grounded explanation, selective review and persistence |
| `backend/app/service.py` | Persistent lifecycle, durable reviewer receipts, thread locks, status projection, safe resume/retry |
| `backend/app/main.py`, `schemas.py` | Authenticated API, async graph streaming, strict request validation and errors |
| `backend/app/app_ui.py`, `ui_events.py` | Incremental Streamlit rendering, review/completion/error handling, saved-thread inspection |
| `backend/app/benchmark/` | Independent 56-case expectations, controlled adapters and actual graph/API evaluation |
| `tests/` | Acceptance tests, real MCP and cached-model Chroma integration, API and Streamlit AppTest |
| `Dockerfile`, `render.yaml` | Correct module packaging, ODBC 18 and persistent-state configuration |

The updated architecture diagram, exact PowerShell setup/start/test commands and feature-status matrix are in the root README.

## Deliberate design choices

SQL Server is retained. A new `AuditRecords` table stores the complete JSON evidence/decision envelope because the old VARCHAR(500) reason field cannot retain versioned policies, reviewer metadata and tool provenance. Each confirmed final decision is also added to the existing `AuditLogs` table, with an idempotency thread marker, so existing SQL dashboards remain useful. No migration is automatic.

MCP uses the maintained official Python SDK's FastMCP server and ClientSession, replacing direct imports of decorated functions. All five tools run in one application-owned stdio process; separating them into three processes adds no authorization benefit locally. Optional model-selected read results cannot replace mandatory verified facts. Only the application possesses the transient write capability, and it is never in the model context.

The application retains Chroma and `all-MiniLM-L6-v2`. All four rules are mandatory for each invoice, so vector retrieval ranks the complete small policy set. Exact version/text/conditions validation detects stale or conflicting indexing. This does not claim a general-purpose RAG relevance benchmark.

Reviewer identity comes from an explicit local token map, not a request field. Review decisions are saved before resume; file locks and a conditional database update protect competing requests. An idempotency key is the thread ID. Same-thread replay is safe; cross-thread duplicate invoice detection is not implemented.

Original policy ambiguity: the small discrepancy OR rule overlaps the mandatory OR rule, and the text leaves a gap between tolerances. Mandatory review wins; the gap is reviewed. Thresholds use strict `<` and `>` as written. The SOW amount basis and category mapping were unspecified; use the larger PO/invoice amount and review unknown categories. These conservative choices are documented for business-owner confirmation.

Web search results are candidate evidence, not a determination of fraud. Name-only matching reduces some obvious mismatches but is not legal-entity verification. Candidate hits, unresolved identity, provider failures and explicit demo results all require review. A reviewer may accept that uncertainty with notes. Missing mandatory invoice/database/policy/SOW evidence cannot be accepted by a reviewer.

## Verification scope

Recorded on 2026-09-07 with Python 3.13: `python -m pytest -q` completed **50 tests in 38.16 seconds**, with no skips. The cached MiniLM/Chroma/MCP test passed after moving ML initialization before the protocol loop. The final evaluator completed **56/56 controlled cases**, with mean actual local execution latency **0.1450832 seconds**, including review rejection/resume and duplicate-decision checks through the API where applicable. `python -m pip check` found no broken requirements; byte-compilation and `git diff --check` passed. After tightening source-field boundaries and expanding evaluator API coverage, six focused Gemini/evaluator tests passed again. Null review-resume metrics mean that a case did not require review; they are not additional measurements.

Tests execute offline with controlled model/tool responses unless their name explicitly refers to MCP or cached Chroma integration. The real MCP graph test uses actual subprocess transport and a temporary SQLite ERP, then restarts the service and confirms a rejected audit record. Streamlit AppTest executes the UI and verifies that state/log rendering updates before the terminal event.

`evaluation/offline-results.json` contains machine-readable per-case outcomes, category reporting, actual execution latency, model/configuration and policy/dependency versions. Offline results must not be presented as live Gemini accuracy. The legacy benchmark filename retains `50` for compatibility but now contains 56 cases. Four text variants per core scenario are robustness fixtures, not 56 independent real invoices.

Live checks remain unverified: Gemini extraction/function calling/explanations, Tavily responses, SQL Server connectivity/migration/inserts, Linux/container build and deployment. Gemini/Tavily/DB connection settings are absent locally. Docker is unavailable. Windows has ODBC Driver 17; the example and Dockerfile use Driver 18. No production data was queried or modified, no deployment was performed and no branch was pushed.

## Limitations before production use

- Text invoices and USD only; no OCR, binary/PDF input or currency conversion.
- Local token authentication, shared audit visibility and one backend worker; no SSO, tenant isolation or distributed orchestration.
- Local checkpoints and evidence records contain sensitive invoice data. Restrict filesystem/database access and apply an organization-approved retention/encryption policy. Model/provider calls intentionally send necessary evidence externally; logs exposed in SSE contain node summaries, not raw invoices or secrets.
- The implementation bounds recovery but does not promise that malformed source data can be repaired. Missing evidence requires correction and a new audit.
- Repeated submissions with different thread IDs can create separate audits for the same invoice. This is not a payment approval ledger or duplicate-payment prevention system.
- Direct dependencies are pinned to the locally tested environment; this is not a fully resolved cross-platform lockfile. Docker packaging is not build-verified.
- New policy versions do not retroactively rewrite paused audits. Reject and resubmit when the new version must apply.

## CV / interview wording

Supported: “Built a Gemini-integrated invoice-audit workflow with actual MCP stdio communication, deterministic Decimal financial controls, versioned policy retrieval, citation validation, persistent human review and an API-driven offline evaluation harness.” Explain that tests use controlled model outputs, and describe the separate real transport and cached embedding tests.

Unsupported: claims of live model accuracy, production deployment/scale, verified corporate fraud detection, production SQL reliability, autonomous payments or enterprise SSO.

SDK references used during implementation: [Google Gen AI Python SDK](https://github.com/googleapis/python-genai) and [official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk). Installed SDK contracts were also exercised locally.
