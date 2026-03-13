#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Bootstrap local development environment from scratch.
#  Usage: bash scripts/bootstrap_dev.sh
# ─────────────────────────────────────────────────────────────
set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()     { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# ── Prerequisites check ────────────────────────────────────────
info "Checking prerequisites..."

command -v docker   >/dev/null || die "Docker not found"
command -v python3  >/dev/null || die "Python 3 not found"
command -v node     >/dev/null || die "Node.js not found"
command -v npm      >/dev/null || die "npm not found"

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
NODE_VERSION=$(node --version)
info "Python ${PYTHON_VERSION} | Node ${NODE_VERSION}"

# ── Environment file ───────────────────────────────────────────
if [ ! -f .env ]; then
    cp .env.example .env
    success "Created .env from .env.example"
    warn "Review .env and update any secrets before proceeding"
fi

# ── Infrastructure ─────────────────────────────────────────────
info "Starting Docker services..."
docker compose up -d

info "Waiting for TimescaleDB..."
until docker compose exec timescaledb pg_isready -U scada -d scada_db 2>/dev/null; do
    sleep 2
done
success "TimescaleDB ready"

# ── Python packages ────────────────────────────────────────────
info "Creating Python virtual environment..."
if [ ! -d venv ]; then
    python3 -m venv venv
fi
source venv/bin/activate

info "Installing Python packages..."
pip install --quiet --upgrade pip
pip install --quiet -e packages/shared -e packages/analytics -e packages/connectors
pip install --quiet -r apps/api/requirements.txt
pip install --quiet -r apps/ingestion/requirements.txt
pip install --quiet pytest pytest-asyncio pytest-cov ruff
success "Python packages installed"

# ── Database migrations ────────────────────────────────────────
info "Running database migrations..."
cd apps/api && alembic upgrade head && cd "$ROOT"
success "Migrations applied"

# ── Sample data ────────────────────────────────────────────────
info "Loading sample SCADA data..."
python3 scripts/ingest_sample.py
success "Sample data loaded"

# ── Frontend ───────────────────────────────────────────────────
info "Installing Node.js dependencies..."
cd apps/frontend && npm install --silent && cd "$ROOT"
success "Frontend dependencies installed"

# ── Done ───────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅  Bootstrap complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo ""
echo "  Start API:       make api-dev"
echo "  Start frontend:  make frontend-dev"
echo "  Run tests:       make test"
echo ""
echo "  API docs:        http://localhost:8000/docs"
echo "  Dashboard:       http://localhost:5173"
echo "  Redpanda UI:     http://localhost:8080"
echo ""
