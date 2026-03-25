# Headline Sentiment Live Polling Application

A production-ready Python application that continuously polls the [Permutable AI](https://permutable.ai) headline sentiment API, stores results in a local database, and exposes the data through a FastAPI service and a Plotly Dash monitoring dashboard.

This application productionises the workflow demonstrated in the companion notebook:
[`notebooks/live/headline_sentiment_polling.ipynb`](../../notebooks/live/headline_sentiment_polling.ipynb)

> **Disclaimer:** This application is provided for informational and research purposes only. Nothing in this application constitutes financial advice or a recommendation to buy, sell, or hold any asset. Sentiment data and indicators surfaced here reflect aggregated model outputs and should not be used as the sole basis for any investment decision.

![Dashboard screenshot](./dashboard.png)

---

## Architecture

```mermaid
flowchart TD
    subgraph compose ["Docker Compose  (local)"]
        poller["poller\nStartup backfill → 15-min loop"]
        api["api  :8000\nFastAPI"]
        dashboard["dashboard  :8050\nPlotly Dash"]
        db[("SQLite\n/data/headline_sentiment.db")]
    end

    ext["Permutable AI API\n/v1/headlines/feed/*"]

    ext -->|"live + historical (paginated)"| poller
    poller -->|upsert| db
    db -->|read-only| api
    api -->|HTTP| dashboard
```

**Three services, one shared volume:**

| Service     | Role                                                                     | Port |
|-------------|--------------------------------------------------------------------------|------|
| `poller`    | Backfills historical data on startup, then polls live data every 15 min  | —    |
| `api`       | FastAPI — serves headlines from the database                             | 8000 |
| `dashboard` | Plotly Dash — monitoring dashboard, auto-refreshes every 60 s            | 8050 |

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) ≥ 24
- [Docker Compose](https://docs.docker.com/compose/) ≥ 2.20 (bundled with Docker Desktop)
- A [Permutable AI](https://permutable.ai) API key

---

## Quickstart

```bash
# 1. Clone and navigate to the app directory
git clone https://github.com/permutable-ai/permutable-examples.git
cd permutable-examples/systematic/headline_asset_sentiment/app/live_polling

# 2. Create your .env file
cp .env.example .env

# 3. Edit .env — set your API key and tickers
#    API_KEY=<your-permutable-ai-api-key>
#    TICKERS=BTC_CRY,ETH_CRY,BZ_COM,EUR_IND
nano .env  # or your preferred editor

# 4. Build and start all services
docker compose up --build

# The poller will backfill the last 7 days of data before the live loop begins.
# Open the dashboard once you see "Backfill complete." in the logs.
```

**Dashboard:** [http://localhost:8050](http://localhost:8050)
**API docs (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)

To run in the background:

```bash
docker compose up --build -d
docker compose logs -f  # tail logs
```

To stop:

```bash
docker compose down         # stop + remove containers
docker compose down -v      # also remove the database volume
```

---

## Configuration Reference

All configuration is managed through environment variables in `.env`. Every service reads from the same file.

| Variable                      | Default                                  | Description                                          |
|-------------------------------|------------------------------------------|------------------------------------------------------|
| `API_KEY`                     | *(required)*                             | Your Permutable AI API key                           |
| `BASE_URL`                    | `https://copilot-api.permutable.ai/v1`  | Permutable AI base URL                               |
| `TICKERS`                     | `BTC_CRY,ETH_CRY,BZ_COM,EUR_IND`       | Comma-separated tickers to monitor                   |
| `MATCH_TYPE`                  | `COMBINED`                               | `EXPLICIT`, `IMPLICIT`, or `COMBINED`                |
| `TOPIC_PRESET`                | `ALL`                                    | Topic preset name or `ALL`                           |
| `LANGUAGE_PRESET`             | `ALL`                                    | `ALL`, `EN`, or any language code                    |
| `SOURCE_PRESET`               | `ALL`                                    | Source preset name or `ALL`                          |
| `SOURCE_COUNTRY_PRESET`       | `ALL`                                    | Source country preset name or `ALL`                  |
| `TOPIC_PROBABILITY_THRESHOLD` | `0.1`                                    | Minimum topic confidence to include (0–1)            |
| `ABS_SENTIMENT_THRESHOLD`     | `0.1`                                    | Minimum \|sentiment_score\| to include (0–1)         |
| `POLL_INTERVAL_SECONDS`       | `900`                                    | Seconds between live polls (default = 15 min)        |
| `BACKFILL_DAYS`               | `7`                                      | Days of history to fetch on startup                  |
| `DB_PATH`                     | `/data/headline_sentiment.db`            | SQLite file path inside containers                   |
| `API_URL`                     | `http://api:8000`                        | Dashboard → API address (use container service name) |
| `REFRESH_INTERVAL_MS`         | `60000`                                  | Dashboard auto-refresh interval in milliseconds      |

> **Tip:** To change the poll interval, update `POLL_INTERVAL_SECONDS` and restart with `docker compose up -d --build`.

---

## Services

### Poller

The poller is the only service that writes to the database. On startup it:

1. Creates the `headline_sentiment` table if it does not exist.
2. Checks the latest stored record per ticker — if data already exists it resumes from that date, otherwise runs a **full historical backfill** (paginated, keyset pagination, up to 90-day lookback).
3. Enters an infinite loop — polls all tickers every `POLL_INTERVAL_SECONDS` seconds using the live endpoint.

The live endpoint always returns the most recent 2-hour window. Because both the historical and live endpoints write via `INSERT OR REPLACE` into the same table, data is automatically de-duplicated across the backfill and live polls.

### API

FastAPI application. Read-only access to the database — the poller is the sole writer.

| Method | Path         | Description                                                               |
|--------|--------------|---------------------------------------------------------------------------|
| `GET`  | `/health`    | Service status and database row count                                     |
| `GET`  | `/headlines` | Raw headlines; params: `ticker`, `hours` (default 24), `limit` (default 1000) |

Swagger UI is available at [http://localhost:8000/docs](http://localhost:8000/docs).

### Dashboard

Plotly Dash monitoring dashboard that auto-refreshes every `REFRESH_INTERVAL_MS` milliseconds (default 60 s). All data is fetched from the API service.

A **ticker dropdown** in the header (defaulting to "All tickers") filters every chart on the page simultaneously.

**Charts displayed:**

- **Stat cards** — total headlines (24 h), mean sentiment, average bullish %, average bearish %
- **30-min smoothed sentiment** — raw scatter + rolling mean over time, one series per ticker
- **Hourly headline count** — stacked bar chart over time showing news flow volume per ticker
- **2 × 2 chart grid:**
  - World map — mean sentiment choropleth by country
  - Mean sentiment by topic — horizontal bar chart (top 15 topics by volume)
  - Headlines by language — grouped bars split by match type (EXPLICIT / IMPLICIT)
  - Mean sentiment by country — horizontal grouped bars split by match type

---

## Example API Usage

```bash
# Health check
curl http://localhost:8000/health

# Last 2 hours of headlines for BTC
curl "http://localhost:8000/headlines?ticker=BTC_CRY&hours=2&limit=100"

# All headlines from the last 7 days
curl "http://localhost:8000/headlines?hours=168&limit=10000"
```

---

## Extending the Application

**Adding tickers:** Update `TICKERS` in `.env` and restart. The poller will backfill new tickers on the next startup.

**Widening the backfill window:** Increase `BACKFILL_DAYS` (max 90 days supported by the API). Delete the database volume first if you want a clean backfill: `docker compose down -v && docker compose up`.

**Changing the poll interval:** Update `POLL_INTERVAL_SECONDS`. Restart with `docker compose up -d --build`.

**Adding new API endpoints:** Edit `api/main.py` and add routes.

---

## Deployment Options

### EC2 / Single VM (Simplest)

Copy the repository to your server and run the same `docker compose up -d` command. Suitable for light workloads and internal tooling.

```bash
# On the server
git clone <repo>
cd live_polling
cp .env.example .env && nano .env
docker compose up -d --build
```

Configure a reverse proxy (nginx / Caddy) to expose the API and dashboard over HTTPS.

---

### AWS ECS + Fargate

For managed container hosting with no servers to maintain.

**Push images to ECR:**

```bash
aws ecr create-repository --repository-name permutable-poller
aws ecr create-repository --repository-name permutable-api
aws ecr create-repository --repository-name permutable-dashboard

# Build and tag
docker build -t permutable-poller ./poller
docker tag permutable-poller:latest <account-id>.dkr.ecr.<region>.amazonaws.com/permutable-poller:latest
# Repeat for api and dashboard

# Push
aws ecr get-login-password | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/permutable-poller:latest
# Repeat for api and dashboard
```

**Poller as an ECS Scheduled Task:**
- Create an ECS Task Definition for the poller with `CMD ["python", "backfill.py"]` for a one-shot backfill, or keep `main.py` for the continuous loop.
- Use an EventBridge rule (`rate(15 minutes)`) to trigger the task — the container runs, polls once, exits. This eliminates the `while True` loop and lets ECS handle scheduling.

**API and Dashboard as ECS Services:**
- Create ECS Services for `api` and `dashboard` with desired count ≥ 1.
- Expose them via an Application Load Balancer (ALB).

**Shared storage:**
- Mount an **EFS volume** at `/data` across all task definitions — SQLite behaves correctly on EFS for single-writer workloads.
- For production durability, see the [Database Upgrade](#database-upgrade-sqlite--postgresql) section below.

**Environment variables:** Store secrets (e.g. `API_KEY`) in **AWS Secrets Manager** and inject via ECS Task Definition secrets.

---

### Kubernetes (EKS / GKE)

**Poller as a CronJob:**

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: sentiment-poller
spec:
  schedule: "*/15 * * * *"
  jobTemplate:
    spec:
      template:
        spec:
          initContainers:
            - name: backfill
              image: <registry>/permutable-poller:latest
              command: ["python", "backfill.py"]
              envFrom:
                - secretRef:
                    name: permutable-secrets
              volumeMounts:
                - name: db-data
                  mountPath: /data
          containers:
            - name: poller
              image: <registry>/permutable-poller:latest
              command: ["python", "-c", "from fetcher import fetch_live_headlines; from db import upsert_headlines; ..."]
          volumes:
            - name: db-data
              persistentVolumeClaim:
                claimName: sentiment-db-pvc
```

**API and Dashboard as Deployments:**
- `Deployment` + `Service` (ClusterIP / LoadBalancer) for each.
- A single `PersistentVolumeClaim` (ReadWriteOnce) shared via the same node, or switch to PostgreSQL.

---

### Airflow (If Already Running)

If your team already operates Airflow, the poller logic integrates cleanly as a DAG:

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

with DAG(
    "headline_sentiment_poller",
    schedule_interval="*/15 * * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=1)},
) as dag:

    poll = PythonOperator(
        task_id="poll_all_tickers",
        python_callable=lambda: [
            upsert_headlines(fetch_live_headlines(t))
            for t in settings.tickers_list
        ],
    )
```

- Run a one-time DAG (`schedule_interval=None`) or a `@once` trigger for the historical backfill.
- The API and Dashboard remain as separate long-running services (ECS / VM / k8s).

---

### Database Upgrade: SQLite → PostgreSQL

The application is designed to make this migration straightforward — only `db.py` in each service needs updating.

**Step 1:** Provision a PostgreSQL instance (e.g. **AWS RDS**, **Cloud SQL**, or a self-hosted container).

**Step 2:** Add `DATABASE_URL` to `.env`:

```env
DATABASE_URL=postgresql://user:password@host:5432/sentiment
```

**Step 3:** Replace `db.py` in each service. Example for the poller:

```python
# poller/db.py  —  PostgreSQL variant
import psycopg2
from contextlib import contextmanager
import os

@contextmanager
def connection():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
```

The `setup_database()` and `upsert_headlines()` functions use standard ANSI SQL with one exception: replace `INSERT OR REPLACE` (SQLite) with PostgreSQL's `INSERT ... ON CONFLICT DO UPDATE` syntax.

```sql
-- PostgreSQL upsert
INSERT INTO headline_sentiment (ticker, publication_time, topic_name, ...)
VALUES (%s, %s, %s, ...)
ON CONFLICT (ticker, publication_time, topic_name)
DO UPDATE SET sentiment_score = EXCLUDED.sentiment_score, fetched_at = EXCLUDED.fetched_at;
```

**Step 4:** Update `requirements.txt` in each service — add `psycopg2-binary` and remove the `sqlite3` dependency (it's part of the Python standard library).

For the API and Dashboard, use **SQLAlchemy** with `pandas.read_sql()` — this requires no changes to `main.py`.

---

## File Structure

```
live_polling/
├── docker-compose.yml        # Orchestrates all three services + shared volume
├── .env.example              # Environment variable template — copy to .env
├── README.md
│
├── poller/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── config.py             # Pydantic Settings — reads all vars from env
│   ├── db.py                 # SQLite setup: setup_database(), upsert_headlines()
│   ├── fetcher.py            # fetch_live_headlines(), fetch_historical_headlines()
│   ├── backfill.py           # backfill_all_tickers() — called once on startup
│   └── main.py               # Entrypoint: setup → backfill → polling loop
│
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── config.py
│   ├── db.py                 # Read-only SQLite connection
│   ├── models.py             # Pydantic response schemas
│   └── main.py               # FastAPI app
│
└── dashboard/
    ├── Dockerfile
    ├── requirements.txt
    ├── config.py
    └── app.py                # Dash monitoring dashboard
```

---

## Troubleshooting

**Dashboard shows "No data — poller starting up…"**
The poller runs the historical backfill before starting the live loop. Wait for the log line `Backfill complete.` — this can take a few minutes depending on the number of tickers and `BACKFILL_DAYS`.

**HTTP 422 from the Permutable API**
Check that your `TICKERS` values are valid ticker symbols included in your licence. Refer to the Permutable AI documentation for valid preset names (`TOPIC_PRESET`, `SOURCE_PRESET`, etc.).

**SQLite database locked**
The poller is the sole writer. If you see lock errors, ensure only one poller instance is running. When scaling the API horizontally, all replicas use the `?mode=ro` read-only URI so they never contend with the writer.

**Port conflicts**
If 8000 or 8050 are in use on your host, change the host-side port mappings in `docker-compose.yml`:
```yaml
ports:
  - "9000:8000"  # host:container
```

---

## Licence

See the repository root for licence information.
