<div align="center">

# 🌬️ Wind Turbine SCADA Analytics Platform

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://reactjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![TimescaleDB](https://img.shields.io/badge/TimescaleDB-Latest-5A3E85?logo=postgresql&logoColor=white)](https://www.timescale.com)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.4-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-22c55e.svg)](LICENSE)

<br/>

**Production-grade wind turbine monitoring, analytics, and ML-powered anomaly detection**

Built on real open-source SCADA data · IEC 61400-12-1 compliant · Cloud-native architecture

<br/>

![Dashboard Preview](docs/assets/dashboard-preview.png)

</div>

---

## 🎯 Overview

This platform delivers **enterprise-grade SCADA analytics** for wind turbine fleets — replacing synthetic demos with real data engineering. It processes 10-minute SCADA intervals from 6 turbines across 5 years of operation, with machine learning anomaly detection and IEC 61400-12-1 compliant power curve analysis.

### Why This Platform?

| Traditional SCADA | This Platform |
|---|---|
| Synthetic / random data | Real Kelmarsh Wind Farm dataset (CC-BY-4.0) |
| Basic threshold alerts | ML anomaly detection — Isolation Forest + statistical models |
| Static PDF reports | Real-time React dashboard with live WebSocket streaming |
| Vendor lock-in | 100% open-source, fully self-hosted |
| $50,000+/year licensing | ~$50/month on a small cloud VM |

---

## ✨ Key Features

### 🔧 Data Engineering
- **Real Dataset** — Kelmarsh Wind Farm: 6 × Senvion MM92 turbines, 5 years, 99+ signals per turbine
- **IEC 61400-12-1 Compliant** — Bin-averaging power curve with air density correction and AEP estimation
- **Data Quality** — Automated validation, completeness monitoring, gap detection
- **Time-Series Optimised** — TimescaleDB hypertables with 90% compression and continuous aggregates

### 🤖 Machine Learning
- **Isolation Forest** — Unsupervised multivariate anomaly detection, scores every 10-min interval
- **Statistical Detector** — Per-signal z-score and IQR baseline, fully interpretable
- **Power Curve Deviation** — Physics-based detection of under-performance vs expected output
- **Explainable AI** — SHAP values surfaced per anomaly event

### 📊 Visualisation
- **Fleet Dashboard** — Live KPI cards: fleet power, wind speed, capacity factor, active alerts
- **Power Curves** — Interactive scatter + IEC bin-averaged curve per turbine
- **Production Charts** — Hourly and daily energy rollups via TimescaleDB `time_bucket`
- **Anomaly Feed** — Real-time severity-coloured event stream across the fleet

### 🏗️ Infrastructure
- **Docker Compose** — One-command local stack: TimescaleDB, Redpanda, Redis, MinIO, Grafana
- **Async FastAPI** — SQLAlchemy 2.0 + asyncpg, WebSocket streaming, automatic OpenAPI docs
- **Kafka-compatible** — Redpanda producers for real-time SCADA replay and ingestion
- **Cloud-Ready** — Kubernetes manifests included for production deployment

---

## 🏛️ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                          DATA SOURCES                             │
│   Kelmarsh SCADA (Zenodo CC-BY-4.0)    OpenMeteo NWP Weather     │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                       STREAMING LAYER                             │
│              Redpanda  (Kafka-compatible)                         │
│   scada.raw.10min  │  scada.anomalies  │  cms.vibration          │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                    TIME-SERIES DATABASE                           │
│                   TimescaleDB (PostgreSQL)                        │
│  Hypertables · Continuous Aggregates · 90% Compression           │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                      API LAYER  (FastAPI)                         │
│   /turbines   /scada   /analytics   /anomalies   /ws (WebSocket) │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                  FRONTEND  (React 18 + TypeScript)                │
│          Recharts · React Query · Zustand · Tailwind CSS          │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Technology Stack

### Backend

| Component | Technology | Purpose |
|---|---|---|
| API Framework | FastAPI 0.110 | Async REST + WebSocket |
| Database | TimescaleDB (PostgreSQL 16) | Time-series storage & rollups |
| ORM | SQLAlchemy 2.0 + asyncpg | Async database access |
| Message Queue | Redpanda | Kafka-compatible stream processing |
| Cache | Redis 7 | Rate limiting, session state |
| ML / AI | scikit-learn, PyOD, SHAP | Anomaly detection & explainability |
| Migrations | Alembic | Database schema versioning |

### Frontend

| Component | Technology | Purpose |
|---|---|---|
| Framework | React 18 + TypeScript 5 | Type-safe UI |
| Data Fetching | React Query (TanStack) | Server state & caching |
| State | Zustand | Client-side state management |
| Charts | Recharts | Power curves, time-series plots |
| Styling | Tailwind CSS | Utility-first dark theme |
| Build | Vite 5 | Fast dev server & bundler |

### Infrastructure

| Component | Technology | Purpose |
|---|---|---|
| Containers | Docker + Compose | Local development stack |
| Orchestration | Kubernetes + Helm | Production deployment |
| Monitoring | Prometheus + Grafana | Metrics & dashboards |
| Object Storage | MinIO | Model artefacts, raw data |
| ML Tracking | MLflow | Experiment registry |

---

## 📐 Project Structure

```
wind-turbine-scada-analytics-v2/
├── apps/
│   ├── api/                  # FastAPI backend
│   │   └── app/
│   │       ├── main.py       # Application entry point
│   │       ├── routers/      # scada, analytics, anomalies, turbines, ws
│   │       └── core/         # Database, Redis, auth
│   ├── frontend/             # React 18 dashboard
│   │   └── src/
│   │       ├── pages/        # FleetDashboard, TurbineDetail
│   │       ├── hooks/        # useApi — React Query data layer
│   │       └── types/        # TypeScript domain types
│   └── ingestion/            # Kafka producers
│       └── producers/        # kelmarsh_producer.py
│
├── packages/                 # Reusable Python packages
│   ├── analytics/            # IEC power curve, anomaly detectors, KPIs
│   ├── connectors/           # Kelmarsh CSV loader, OpenMeteo client
│   └── shared/               # Pydantic models, settings, logging
│
├── infra/
│   ├── timescaledb/          # schema.sql — hypertables, aggregates, seed data
│   ├── kafka/                # Topic definitions
│   └── kubernetes/           # Helm charts & manifests
│
├── data/sample/              # Bundled sample CSVs for tests & demos
├── notebooks/                # Jupyter exploration & model development
├── scripts/                  # Bootstrap, download, ingest helpers
└── tests/                    # Pytest unit & integration tests
```

---

## 🚀 Quick Start

### Prerequisites

| Tool | Version | Check |
|---|---|---|
| Docker Desktop | 24.0+ | `docker --version` |
| Python | 3.11+ | `python3 --version` |
| Node.js | 20+ | `node --version` |
| Git | Any | `git --version` |

### 1. Clone & Configure

```bash
git clone https://github.com/LMBM84/wind-turbine-scada-analytics_F.git
cd wind-turbine-scada-analytics_F
cp .env.example .env
```

### 2. Start Infrastructure

```bash
docker compose up -d
```

Starts: TimescaleDB · Redpanda · Redis · MinIO · MLflow · Grafana

### 3. Set Up Python Environment

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -e packages/shared -e packages/analytics -e packages/connectors
pip install -r apps/api/requirements.txt
```

### 4. Initialise Database

```bash
docker compose exec -T timescaledb psql -U scada -d scada_db -f /dev/stdin < infra/timescaledb/schema.sql
python3 scripts/ingest_sample.py
```

### 5. Start API

```bash
cd apps/api
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Start Frontend

```bash
cd apps/frontend
npm install
npm run dev
```

### 7. Open Dashboard

| Service | URL |
|---|---|
| **Dashboard** | http://localhost:5173 |
| **API Docs** | http://localhost:8000/docs |
| **Redpanda UI** | http://localhost:8080 |
| **Grafana** | http://localhost:3001 |
| **MLflow** | http://localhost:5001 |

---

## 📡 Data Sources

### Kelmarsh Wind Farm — Primary Dataset

| Attribute | Value |
|---|---|
| Location | Kelmarsh, Northamptonshire, UK |
| Turbines | 6 × Senvion MM92 (2.05 MW each, 12.3 MW total) |
| Period | 2016 – 2024 |
| Resolution | 10-minute averages |
| Signals | 99+ per turbine |
| License | **CC-BY-4.0** (free for commercial use) |
| Source | [Zenodo DOI: 10.5281/zenodo.5841834](https://doi.org/10.5281/zenodo.5841834) |

**Signals include:** Wind speed/direction · Active & reactive power · Rotor RPM · Pitch angle · Gearbox, generator & main bearing temperatures · Grid voltage & frequency · Status codes

### OpenMeteo NWP — Weather Forecast

| Attribute | Value |
|---|---|
| Type | Numerical Weather Prediction API |
| Resolution | Hourly, real-time |
| License | CC-BY-4.0 |
| Use | Wind forecast overlay, density correction |

---

## 🧪 Tests

```bash
# Full test suite
pytest tests/ -v --cov=packages

# Unit tests only (no database required)
pytest tests/ -v -m "not integration"
```

| Test File | Coverage |
|---|---|
| `tests/test_connector.py` | Kelmarsh CSV loading, data validation |
| `tests/test_power_curve.py` | IEC 61400-12-1 algorithm correctness |

---

## 🔑 Environment Variables

Key variables in `.env` (full list in `.env.example`):

```env
# Database
DATABASE_URL=postgresql+asyncpg://scada:scada@localhost:5432/scada_db

# Kafka
KAFKA_BROKERS=localhost:9092
KAFKA_TOPIC_SCADA_RAW=scada.raw.10min

# Security
SECRET_KEY=change-me-in-production

# MLflow
MLFLOW_TRACKING_URI=http://localhost:5001
```

---

## 📊 API Reference

The API is fully documented at `/docs` (Swagger UI) and `/redoc`. Key endpoints:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/turbines/` | List all turbines |
| `GET` | `/api/v1/scada/{id}/readings` | Paginated SCADA readings |
| `GET` | `/api/v1/scada/{id}/latest` | Most recent reading |
| `GET` | `/api/v1/analytics/fleet/overview` | Live fleet snapshot |
| `GET` | `/api/v1/analytics/{id}/power-curve` | IEC power curve |
| `GET` | `/api/v1/analytics/{id}/kpis` | Operational KPIs |
| `GET` | `/api/v1/analytics/{id}/production` | Energy rollup |
| `GET` | `/api/v1/anomalies/{id}` | Anomaly event list |
| `POST` | `/api/v1/anomalies/run-detection` | Trigger ML detection |
| `WS` | `/ws/turbines/{id}/live` | Real-time SCADA stream |
| `WS` | `/ws/fleet/anomalies` | Live anomaly broadcast |

---

## 🗺️ Roadmap

- [x] Core SCADA data pipeline (ingest, validate, store)
- [x] IEC 61400-12-1 power curve computation
- [x] Isolation Forest anomaly detection
- [x] Fleet dashboard with live KPIs
- [x] TimescaleDB continuous aggregates
- [ ] LSTM autoencoder for sequence-aware detection
- [ ] Turbine detail page with full signal explorer
- [ ] JWT authentication & user roles
- [ ] GitHub Actions CI/CD pipeline
- [ ] Kubernetes Helm chart deployment
- [ ] SHAP explainability UI overlay

---

## 🤝 Contributing

Contributions are welcome. Please open an issue first to discuss what you'd like to change.

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'Add your feature'`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request

---

## 📄 License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.

The Kelmarsh dataset is licensed under **CC-BY-4.0** — attribution required.

---

<div align="center">

Built with ☕ and 🌬️ by [LMBM84](https://github.com/LMBM84)

</div>

