# OpsPilot Project Specification

This is the concise current specification. The full historical implementation
specification remains in `OpsPilot — Master Implementation Specification.md`.

## Purpose

OpsPilot is an AI-assisted incident intelligence platform with controlled,
simulator-only remediation. It gathers operational evidence, produces a
structured investigation, applies server-side risk and policy controls, obtains
human approval where required, executes through ToolGateway, and verifies actual
simulator recovery.

## Product boundaries

- PostgreSQL is authoritative for domain state.
- Redis/Celery provide asynchronous processing.
- Qdrant is a rebuildable derived RAG index.
- The simulator is the only execution environment.
- AI output and retrieved documents are untrusted.
- Verification, not tool success, determines automated resolution.
- Critical actions and policy/approval bypasses are never executable.

## Current status

The project is **ready for controlled local end-to-end validation and demo
preparation**, but is **not production-ready**. See `docs/FINAL_READINESS.md`
for evidence, blockers, and limitations.