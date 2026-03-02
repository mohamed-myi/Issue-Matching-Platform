# IssueIndex

IssueIndex is a GitHub issue discovery platform. It indexes open issues from active repositories, scores them for quality, stores embeddings in PostgreSQL with `pgvector`, and serves both search and personalized recommendations through a Next.js frontend and a FastAPI backend.

The repository is a monorepo with four main parts:

- `apps/frontend`: Next.js 16 application
- `apps/backend`: FastAPI API and profile worker services
- `apps/workers`: ingestion and maintenance job runner
- `packages/database` and `packages/shared`: shared models, migrations, constants, and utilities

## What the product does

- Indexes open GitHub issues from active repositories across multiple languages
- Filters low-quality issues with a structural quality score before indexing
- Supports hybrid issue search with semantic retrieval plus full-text ranking
- Provides a personalized feed based on manual intent, resume data, and GitHub activity
- Supports bookmarks, notes, similar issues, repository filters, and taxonomy-backed onboarding
- Uses GitHub and Google OAuth for sign-in, plus a separate GitHub connect flow for profile enrichment

## How it works

```text
GitHub repos/issues
  -> Scout discovers repositories by language and activity
  -> Gatherer streams issues via GitHub GraphQL
  -> Quality gate filters weak issues
  -> Embedder generates 256-dim vectors
  -> Persistence writes repositories/issues into Postgres + pgvector

User profile
  -> Intent text + taxonomy choices
  -> Resume parsing and embedding
  -> GitHub activity analysis and embedding
  -> Weighted combined vector

Retrieval
  -> Search: vector similarity + BM25-style full-text fusion
  -> Feed: personalized similarity ranking with freshness adjustment
  -> Trending fallback when no profile vector exists
```

## Architecture at a glance

### Frontend

- Next.js App Router
- React 19
- TanStack Query for API state
- Tailwind CSS 4 and Radix UI primitives

### Backend API

- FastAPI app with routes for auth, search, feed, profile, bookmarks, issues, repositories, and taxonomy
- Cookie-based sessions with GitHub and Google OAuth
- Redis-backed caching and rate limiting, with in-memory fallback when Redis is unavailable
- Local Nomic MoE embeddings truncated to 256 dimensions

### Background processing

- `collector`: discovers repositories and stages high-quality issues
- `collector_then_embedder`: collector followed by embedding in one execution
- `embedder`: turns staged issues into vectorized rows in `ingestion.issue`
- `janitor`: prunes low-survival-score issues
- `reco_flush`: flushes recommendation events from Redis into Postgres analytics
- Separate FastAPI worker services handle async resume parsing and GitHub profile enrichment

### Storage and infrastructure

- PostgreSQL 16 with `pgvector`
- Redis for cache, queue-like analytics buffering, and rate limiting
- Cloud Tasks for async profile jobs in production
- Dockerfiles for frontend, API, workers, and worker services under `deploy/`

## Repository layout

```text
.
├── apps
│   ├── backend
│   │   ├── gim_backend
│   │   │   ├── api
│   │   │   ├── core
│   │   │   ├── ingestion
│   │   │   ├── services
│   │   │   └── workers
│   │   └── tests
│   ├── frontend
│   │   ├── src/app
│   │   ├── src/components
│   │   └── src/lib
│   └── workers
│       ├── gim_workers
│       └── tests
├── packages
│   ├── database
│   │   ├── gim_database
│   │   ├── migrations
│   │   └── tests
│   └── shared
│       └── gim_shared
└── deploy
```

## Core runtime surfaces

### Public

- Landing page stats and trending issues
- Repository and taxonomy lookup endpoints
- Issue detail and similar issue discovery
- Search API with anonymous rate limiting

### Authenticated

- Personalized feed
- Profile creation and onboarding
- Resume upload and GitHub profile enrichment
- Bookmark and note management
- Recommendation event logging
- Account and session management

## Local development

### Prerequisites

- Python 3.11+ recommended, with 3.12 matching the deployment images
- Node.js 20+
- PostgreSQL 16 with `pgvector`
- Redis 7+ recommended
- GitHub OAuth app and Google OAuth app if you want to test login flows

### 1. Create the root environment file

```bash
cp .env.example .env.local
```

At minimum, set these values in `.env.local`:

| Variable | Required for | Notes |
| --- | --- | --- |
| `DATABASE_URL` | API, workers | Async Postgres URL |
| `DIRECT_DATABASE_URL` | Alembic migrations | Usually the same as `DATABASE_URL` locally |
| `NEXT_PUBLIC_API_BASE_URL` | Frontend | Example: `http://localhost:8000` |
| `FERNET_KEY` | Auth and linked account token storage | Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `FINGERPRINT_SECRET` | Session fingerprinting | Use a long random string |
| `REDIS_URL` | Cache, rate limits, analytics queue | Recommended locally; API falls back to memory if missing |

Optional but commonly needed:

- `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET`
- `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`
- `FRONTEND_BASE_URL`
- `COOKIE_DOMAIN`
- `GIT_TOKEN` for the collector job
- `EMBED_WORKER_URL`, `RESUME_WORKER_URL`, `GCP_PROJECT`, and `CLOUD_TASKS_QUEUE` for production-style async profile jobs

### 2. Install Python packages

Create one virtual environment at the repository root and install the editable packages:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e packages/shared -e packages/database -e "apps/backend[dev,ml,resume]" -e "apps/workers[dev,redis]"
```

Notes:

- `apps/backend[ml]` installs the local embedding stack
- `apps/backend[resume]` installs Docling and GLiNER for resume parsing
- `apps/workers[redis]` installs the Redis client used by the worker processes

### 3. Install frontend dependencies

```bash
cd apps/frontend
npm ci
cd ../..
```

### 4. Prepare PostgreSQL

Create a local database and enable `pgvector`:

```sql
CREATE DATABASE issueindex;
\c issueindex
CREATE EXTENSION IF NOT EXISTS vector;
```

Then run migrations:

```bash
cd packages/database
alembic upgrade head
cd ../..
```

### 5. Start the API

Run the FastAPI app from the repository root so it reads the root `.env.local`:

```bash
source .venv/bin/activate
uvicorn gim_backend.main:app --reload --port 8000
```

Useful local endpoints:

- API base: `http://localhost:8000`
- Health check: `http://localhost:8000/health`
- Interactive API docs: `http://localhost:8000/docs`

### 6. Start the frontend

The frontend dev script copies `NEXT_PUBLIC_*` values from the root `.env.local` into `apps/frontend/.env.local` automatically.

```bash
cd apps/frontend
npm run dev
```

Frontend URL: `http://localhost:3000`

### 7. Run background jobs

From the repository root, with the Python virtualenv active:

```bash
JOB_TYPE=collector python -m gim_workers
JOB_TYPE=collector_then_embedder python -m gim_workers
JOB_TYPE=embedder python -m gim_workers
JOB_TYPE=janitor python -m gim_workers
JOB_TYPE=reco_flush python -m gim_workers
```

## Local development behavior to know about

- The API can run without Redis, but cache, analytics buffering, and distributed rate limiting will degrade to in-memory behavior or become unavailable.
- In development mode, Cloud Tasks uses a mock client by default. Manual intent-based personalization works locally, but async resume and GitHub profile jobs are not automatically dispatched unless you wire the API to real Cloud Tasks and worker URLs.
- The embedding model is large. Embedding-heavy flows and the embedder worker need noticeably more memory than the basic API.
- The frontend build excludes mock handlers from production output, but mock mode can still be enabled locally with `NEXT_PUBLIC_MOCK_API=true`.

## Testing

### Backend

```bash
cd apps/backend
python -m pytest tests/unit -v
python -m pytest tests/integration -v
```

The integration suite includes opt-in groups controlled by environment flags:

- `RUN_DOCKER_INTEGRATION=1`
- `RUN_MODEL_INTEGRATION=1`
- `RUN_LIVE_API_INTEGRATION=1`
- `RUN_REAL_DB_INTEGRATION=1`
- `RUN_PROD_DB_TESTS=1`

### Workers

```bash
cd apps/workers
python -m pytest tests -v
```

### Database package

```bash
cd packages/database
python -m pytest tests -v
```

### Frontend

```bash
cd apps/frontend
npm run lint
npm run build
```

## Deployment shape

The repository is set up for a GCP-style deployment:

- Frontend deployed as a standalone Next.js app
- FastAPI API deployed separately
- Ingestion and maintenance jobs run as containerized worker jobs
- Resume and embed worker services receive Cloud Tasks requests
- PostgreSQL and Redis back the application state, retrieval data, analytics, and queues

Relevant container definitions:

- `deploy/frontend.Dockerfile`
- `deploy/api.Dockerfile`
- `deploy/workers.Dockerfile`
- `deploy/worker-embed.Dockerfile`
- `deploy/worker-resume.Dockerfile`

## Project highlights

- Search combines semantic embeddings with keyword retrieval instead of relying on one ranking strategy
- Personalized recommendations are built from multiple optional profile sources rather than a mandatory onboarding flow
- The data model separates ingestion, analytics, identity, staging, and profile concerns cleanly
- The repo includes both product-facing apps and operational job runners in one place, which makes end-to-end reasoning easier but requires a disciplined local setup
