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

## 📄 License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.

The Kelmarsh dataset is licensed under **CC-BY-4.0** — attribution required.

---

<div align="center">

Built with ☕ and 🌬️ by [LMBM84](https://github.com/LMBM84)

</div>

