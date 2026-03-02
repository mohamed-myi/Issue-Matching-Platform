# Backend API (`apps/backend`)

FastAPI backend for IssueIndex.

## Responsibilities

- OAuth login/link/connect flows and session management
- Search and feed APIs (hybrid retrieval + personalization)
- Profile/onboarding/resume/GitHub orchestration
- Cloud Tasks enqueueing for profile background jobs
- Recommendation/search analytics write APIs

## Key Runtime Facts

- Embeddings use local Nomic MoE with 256-dim Matryoshka truncation
- Search responses may set `total_is_capped=true` when stage-1 candidate limits are hit
- Worker `/tasks/*` endpoints require Cloud Tasks OIDC in production

## Common Commands

```bash
cd apps/backend
python3 -m pytest tests/unit -q
python3 -m pytest tests/integration -q
ruff check .
```

See `/Users/mohamedibrahim/II/docs/operations/local-dev.md` for full setup and opt-in integration test flags.
