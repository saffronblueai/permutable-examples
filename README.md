# permutable-examples

Example implementations, integrations, and research notebooks for [Permutable AI](https://permutable.ai) products.

This repository provides end-to-end reference material — from single-file Jupyter notebooks through to example containerised applications — covering the full workflow from live data ingestion to signal research and backtesting.

> **Disclaimer:** All examples are provided for informational and research purposes only. Nothing here constitutes financial advice or a recommendation to buy, sell, or hold any asset.

---

## Contents

- [Products Covered](#products-covered)
- [Repository Structure](#repository-structure)
- [Examples](#examples)
  - [Headline Asset Sentiment](#headline-asset-sentiment)
  - [Regional Macro Sentiment](#regional-macro-sentiment)
- [Getting Started](#getting-started)
- [Prerequisites](#prerequisites)
- [API Access](#api-access)

---

## Products Covered

| Product | Description | API Endpoint Prefix |
|---|---|---|
| **Headline Asset Sentiment** | Per-headline and pre-aggregated hourly sentiment scores for assets, by topic and match type | `/v1/headlines/` |
| **Regional Macro Sentiment** | Pre-aggregated hourly macro-geopolitical sentiment indices by country, topic, and index type | `/v1/regional-macro/` |

---

## Repository Structure

```
permutable-examples/
└── systematic/
    ├── headline_asset_sentiment/
    │   ├── app/
    │   │   ├── live_headline_polling/   # Production app — raw headline feed
    │   │   └── live_index_polling/      # Production app — pre-aggregated index feed
    │   └── notebooks/
    │       ├── live/                    # Live polling integration guides
    │       └── backtesting/             # Signal research and backtesting
    └── regional_macro_sentiment/
        ├── app/
        │   └── live_index_polling/      # Production app — regional macro index feed
        └── notebooks/
            └── backtesting/             # FX cross-country signal research
```

---

## Examples

### Headline Asset Sentiment

#### Live Polling Notebooks

Quick-start integration guides that run end-to-end in a single Jupyter notebook using a local SQLite database. Ideal for exploring the API, prototyping, and monitoring.

| Notebook | Endpoint Used | Description |
|---|---|---|
| [`headline_sentiment_polling.ipynb`](systematic/headline_asset_sentiment/notebooks/live/headline_sentiment_polling.ipynb) | Raw feed `/v1/headlines/feed/live` | Polls per-headline sentiment, bins into 15-min periods, derives a rolling average sentiment indicator and heatmap |
| [`index_sentiment_polling.ipynb`](systematic/headline_asset_sentiment/notebooks/live/index_sentiment_polling.ipynb) | Pre-aggregated index `/v1/headlines/index/ticker/live` | Polls the hourly sentiment index directly, derives average sentiment and a HIGH / NEUTRAL / LOW indicator |

Both notebooks follow the same structure:

1. Authenticate with the API
2. Dry-run a single poll to validate connectivity and inspect the schema
3. Persist results to a local SQLite database
4. Run the live polling loop (15-min interval)
5. Visualise the accumulated window (sentiment time series, heatmap, indicator)
6. Demonstrate an aggregation example for research and monitoring

#### Live Polling Applications

Example containerised applications that extend the notebook workflows into a three-service Docker setup. They are reference implementations intended to illustrate the integration pattern — review and adapt them before using in any real environment.

| Service | Role | Port |
|---|---|---|
| `poller` | Historical backfill on startup, then polls every 15 min | — |
| `api` | FastAPI — serves stored data and derived indicators | 8000 |
| `dashboard` | Plotly Dash — monitoring dashboard, auto-refreshes every 60 s | 8050 |

| Application | Feed Type | README |
|---|---|---|
| [`live_headline_polling`](systematic/headline_asset_sentiment/app/live_headline_polling/) | Per-headline raw feed | [README](systematic/headline_asset_sentiment/app/live_headline_polling/README.md) |
| [`live_index_polling`](systematic/headline_asset_sentiment/app/live_index_polling/) | Pre-aggregated hourly index | [README](systematic/headline_asset_sentiment/app/live_index_polling/README.md) |

Both apps are configured entirely through a `.env` file and start with a single command:

```bash
cp .env.example .env  # add your API key and tickers
docker compose up --build
```

#### Backtesting Notebooks

Signal research notebooks that evaluate historical headline sentiment as a predictor of asset returns. They implement a full quantitative pipeline: rolling transforms → Pearson correlation → Benjamini-Hochberg FDR correction → walk-forward validation → cross-ticker grading.

| Notebook | Sentiment Source | Description |
|---|---|---|
| [`headline_cross_ticker_signal_assessment.ipynb`](systematic/headline_asset_sentiment/notebooks/backtesting/headline_cross_ticker_signal_assessment.ipynb) | Raw headline feed | Correlates per-headline sentiment aggregates with forward asset returns across topics, regimes, and horizons |
| [`index_cross_ticker_signal_assessment.ipynb`](systematic/headline_asset_sentiment/notebooks/backtesting/index_cross_ticker_signal_assessment.ipynb) | Pre-aggregated index | Same pipeline applied to the hourly index endpoint; faster to run and suitable for longer lookbacks |

**Methodology:**

```
Sentiment series
    → rolling z-score / rolling mean (windows: 10d, 21d, 63d)
    → Pearson correlation + t-stat p-value
    → Benjamini-Hochberg FDR correction (per regime)
    → walk-forward validation (60% IS / 40% OOS)
    → cross-ticker grade (A–F) and ranking tables
```

**Outputs:** Three ranked summary tables — overall ticker grade, top sentiment driver per ticker, and top sentiment group per ticker — with regime breakdowns (BOTH / UP / DOWN) across 7d, 1m, and 3m return horizons.

---

### Regional Macro Sentiment

#### Live Polling Application

Production-ready application for the regional macro-geopolitical sentiment index. Identical three-service architecture (`poller` / `api` / `dashboard`) as the headline apps, adapted for the regional macro endpoint.

| Application | README |
|---|---|
| [`live_index_polling`](systematic/regional_macro_sentiment/app/live_index_polling/) | [README](systematic/regional_macro_sentiment/app/live_index_polling/README.md) |

The macro index partitions data by `topic_name` and `index_type` (`DOMESTIC` / `INTERNATIONAL`), giving separate sentiment series for domestically-sourced vs internationally-sourced headlines for each country and topic.

#### Backtesting Notebook

| Notebook | Description |
|---|---|
| [`fx_cross_currency_signal_assessment.ipynb`](systematic/regional_macro_sentiment/notebooks/backtesting/eval/fx_cross_currency_signal_assessment.ipynb) | Evaluates regional macro sentiment indices as predictors of FX currency index returns across 7 countries |

This notebook applies the same quantitative methodology as the headline asset backtesting pipeline — rolling transforms, Pearson correlation, BH FDR correction, and walk-forward validation — adapted for:

- **Sentiment source:** Regional macro sentiment zip archives partitioned by `topic_name` and `index_type`
- **Correlation target:** Daily FX currency index prices (`AUD_IND`, `CNY_IND`, `EUR_IND`, `GBP_IND`, `JPY_IND`, `USD_IND`)
- **Country coverage:** Australia, China, France, Germany, Japan, United Kingdom, United States

**Derived sentiment metrics (from raw index columns):**

| Metric | Formula | Measures |
|---|---|---|
| `sentiment_avg` | `sentiment_sum / headline_count` | Average directional sentiment |
| `sentiment_std_daily` | std of hourly `sentiment_avg` | Intra-day disagreement |
| `headline_count` | sum of hourly counts | News volume / attention |

---

## Getting Started

### Run a notebook

```bash
git clone https://github.com/permutable-ai/permutable-examples.git
cd permutable-examples

pip install jupyter pandas numpy scipy matplotlib seaborn
jupyter notebook
```

Open any notebook under `systematic/*/notebooks/` and follow the inline instructions.

### Start a live polling app

```bash
# Example: headline index polling app
cd systematic/headline_asset_sentiment/app/live_index_polling

cp .env.example .env
# Edit .env — set API_KEY and TICKERS

docker compose up --build
```

- Dashboard: [http://localhost:8050](http://localhost:8050)
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

See the app-level READMEs for full configuration references and deployment options (EC2, ECS/Fargate, Kubernetes, Airflow).

---

## Prerequisites

| Requirement | Minimum version | Used by |
|---|---|---|
| Python | 3.9+ | All notebooks |
| Docker | 24+ | Production apps |
| Docker Compose | 2.20+ | Production apps |
| Jupyter | Any recent | Notebooks |

Python package requirements for each app are in the service-level `requirements.txt` files. Notebook dependencies are installed in the first cell of each notebook.

---

## API Access

All examples require a **Permutable AI API key**. Set it as the `API_KEY` environment variable (apps) or enter it via `getpass` when prompted (notebooks).

- Documentation: [docs.permutable.ai](https://docs.permutable.ai)
- Account and key management: [permutable.ai](https://permutable.ai)

---

## Licence

See [LICENCE](LICENCE) for details.
