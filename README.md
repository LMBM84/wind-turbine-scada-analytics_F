# 🌬️ Wind Turbine SCADA Analytics Platform v2

Production-grade wind turbine monitoring, analytics, and anomaly detection system built on real datasets, open-source tooling, and modern cloud-native infrastructure.

---

## 📐 Architecture

```
wind-turbine-scada-analytics-v2/
├── apps/
│   ├── frontend/       # React 18 + TypeScript dashboard (Deck.gl, Recharts)
│   ├── api/            # FastAPI async REST + WebSocket backend
│   └── ingestion/      # Kafka producers / data ingestion pipeline
├── packages/
│   ├── analytics/      # Power curve, KPIs, anomaly detection (ML)
│   ├── connectors/     # Dataset loaders (Kelmarsh, La Haute Borne, OpenMeteo)
│   └── shared/         # Pydantic schemas, config, logging utilities
├── infra/
│   ├── timescaledb/    # DB schema, hypertables, continuous aggregates
│   ├── kafka/          # Topic definitions, consumer group configs
│   └── kubernetes/     # Helm charts and K8s manifests
├── data/sample/        # Tiny CSVs for demos and unit tests
├── notebooks/          # Jupyter exploration and model development
├── scripts/            # Dataset download and dev bootstrap helpers
└── tests/              # Pytest unit + integration tests
```

---

## 🚀 Quick Start (Local Dev)

### Prerequisites
- Docker 24.0+ & Docker Compose v2
- Python 3.11+
- Node.js 20+
- `make` (optional but recommended)

### 1. Clone & Configure

```bash
git clone https://github.com/yourorg/wind-turbine-scada-analytics-v2.git
cd wind-turbine-scada-analytics-v2
cp .env.example .env          # edit secrets as needed
```

### 2. Start Infrastructure

```bash
make dev-up
# OR: docker compose up -d
```

This starts: TimescaleDB, Redpanda (Kafka), Redis, MLflow, MinIO.

### 3. Bootstrap Database & Ingest Sample Data

```bash
make bootstrap          # runs migrations + loads sample data
# OR manually:
cd apps/api && alembic upgrade head
python ../../scripts/download_kelmarsh.py --sample
python ../../scripts/ingest_sample.py
```

### 4. Start API

```bash
cd apps/api
pip install -e ../../packages/shared ../../packages/analytics ../../packages/connectors
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 5. Start Frontend

```bash
cd apps/frontend
npm install
npm run dev
# → http://localhost:5173
```

### 6. Run Ingestion Worker (optional)

```bash
cd apps/ingestion
python -m producers.kelmarsh_producer --turbine K1 --replay
```

---

## 🔑 Key URLs

| Service       | URL                          |
|---------------|------------------------------|
| Frontend      | http://localhost:5173        |
| API Docs      | http://localhost:8000/docs   |
| Redpanda UI   | http://localhost:8080        |
| MLflow        | http://localhost:5001        |
| Grafana       | http://localhost:3001        |
| MinIO Console | http://localhost:9001        |

---

## 🧪 Tests

```bash
make test
# OR: pytest tests/ -v --cov=packages
```

---

## 📡 Data Sources

| Dataset          | Turbines | Period    | Resolution | License   |
|------------------|----------|-----------|------------|-----------|
| Kelmarsh         | 6 × MM92 | 2016–2021 | 10 min     | CC-BY-4.0 |
| La Haute Borne   | 4 × MM82 | 2013–2020 | 10 min     | Open      |
| OpenMeteo NWP    | —        | Real-time | Hourly     | CC-BY-4.0 |

---

## 🏗️ Technology Stack

**Backend:** FastAPI · TimescaleDB · Redpanda · Redis · Celery · SQLAlchemy 2.0  
**ML:** PyTorch · scikit-learn · PyOD · SHAP · MLflow  
**Frontend:** React 18 · TypeScript · Zustand · React Query · Deck.gl · Recharts · Vite  
**Infra:** Docker · Kubernetes · Helm · Prometheus · Grafana · Jaeger · Vault  

---

## 📄 License

MIT — see [LICENSE](LICENSE)
