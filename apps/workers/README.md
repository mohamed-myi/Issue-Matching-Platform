# Workers (`apps/workers`)

Cloud Run Jobs entrypoint and job orchestration for ingestion + maintenance.

## Jobs (`JOB_TYPE`)

- `collector` - Scout + gather + quality gate into `staging.pending_issue`
- `embedder` - Read staging, generate 256-dim embeddings, persist to `ingestion.issue`
- `janitor` - Prune low-survival-score issues
- `reco_flush` - Flush recommendation events from Redis to Postgres analytics

## Run Locally

```bash
cd apps/workers
JOB_TYPE=collector python -m gim_workers
JOB_TYPE=embedder python -m gim_workers
JOB_TYPE=janitor python -m gim_workers
JOB_TYPE=reco_flush python -m gim_workers
```

## Tests

```bash
cd apps/workers
python3 -m pytest tests -q
```
