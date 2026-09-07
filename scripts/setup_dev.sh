#!/usr/bin/env bash
# ============================================================================
# LangChain EvalTask — Setup développement local
# Génère le .env dev et démarre Redis + serveur
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"

echo "🔧 Setup développement LangChain EvalTask"
echo "==========================================="

# --- Générer .env si absent ---
if [ ! -f "$ENV_FILE" ]; then
  echo "📄 Création de $ENV_FILE..."
  cat > "$ENV_FILE" <<'EOF'
# ============================================================================
# LangChain EvalTask Server — Configuration DÉVELOPPEMENT
# Généré par scripts/setup_dev.sh — NE PAS COMMITTER
# ============================================================================

# --- Serveur ---
APP_NAME=LangChain EvalTask Server (DEV)
APP_VERSION=2.0.0-dev
PORT=8000
DEBUG=true
HOST=0.0.0.0
ALLOWED_ORIGINS=*

# --- JWT (doit correspondre à LANGCHAIN_SECRET côté Rails .env) ---
JWT_SECRET=dev-shared-secret-evaltask-2026
JWT_ALGORITHM=HS256
JWT_EXPIRY_LEEWAY_SECONDS=60

# --- OpenRouter ---
OPENROUTER_DEFAULT_MODEL=z-ai/glm-5.2
OPENROUTER_FALLBACK_MODEL=google/gemma-3-27b-it
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_TIMEOUT_SECONDS=60
OPENROUTER_MAX_RETRIES=2

# --- Embeddings ---
EMBEDDING_PROVIDER_URL=https://openrouter.ai/api/v1
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_API_KEY=

# --- ChromaDB ---
CHROMA_PERSIST_DIR=./data/chromadb
CHROMA_MAX_RESULTS=5

# --- Redis ---
REDIS_URL=redis://localhost:6379/0
CONVERSATION_TTL_SECONDS=7200
CONVERSATION_MAX_MESSAGES=50

# --- Limites LLM ---
MAX_TOOL_ROUNDS=5
MAX_TOKENS=4096
TEMPERATURE=0.7

# --- Rate limiting (permissif en dev) ---
RATE_LIMIT_REQUESTS_PER_MINUTE=120
RATE_LIMIT_TOKENS_PER_DAY=1000000

# --- Budget ---
BUDGET_ALERT_THRESHOLD_USD=50.0
COST_TRACKING_ENABLED=false

# --- Observabilité ---
LOG_LEVEL=DEBUG
TRACE_SAMPLING_RATE=1.0
METRICS_ENABLED=true

# --- Sécurité ---
MAX_INPUT_LENGTH=20000
MAX_HISTORY_MESSAGES=50
EOF
  echo "   ✅ .env créé avec secret JWT de dev"
else
  echo "   ⏭  .env existe déjà, pas de modification"
fi

# --- Créer les répertoires de données ---
mkdir -p "$PROJECT_DIR/data/chromadb"
mkdir -p "$PROJECT_DIR/data/knowledge"
echo "📁 Répertoires data/ créés"

# --- Vérifier Redis ---
if command -v redis-cli &>/dev/null && redis-cli ping &>/dev/null 2>&1; then
  echo "✅ Redis est déjà démarré"
else
  echo "⚠️  Redis n'est pas accessible."
  echo "   Options :"
  echo "   1) brew services start redis     (macOS Homebrew)"
  echo "   2) docker run -d --name redis-dev -p 6379:6379 redis:7-alpine"
  echo "   3) docker compose up redis -d    (depuis ce projet)"
fi

# --- Vérifier Python ---
if command -v python3 &>/dev/null; then
  PYTHON_VERSION=$(python3 --version 2>&1)
  echo "✅ $PYTHON_VERSION"
else
  echo "❌ Python3 non trouvé. Installez Python 3.11+"
  exit 1
fi

# --- Installer les dépendances ---
if [ ! -d "$PROJECT_DIR/.venv" ]; then
  echo "📦 Création du virtualenv..."
  python3 -m venv "$PROJECT_DIR/.venv"
fi

echo "📦 Installation des dépendances..."
source "$PROJECT_DIR/.venv/bin/activate"
pip install -q -r "$PROJECT_DIR/requirements.txt"

echo ""
echo "==========================================="
echo "✅ Setup terminé !"
echo ""
echo "Pour démarrer le serveur LangChain :"
echo "  cd $PROJECT_DIR"
echo "  source .venv/bin/activate"
echo "  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
echo ""
echo "Pour démarrer Redis (si pas fait) :"
echo "  docker compose up redis -d"
echo ""
echo "⚠️  Assurez-vous que le .env Rails contient :"
echo "  AI_PROVIDER=langchain"
echo "  LANGCHAIN_SERVER_URL=http://localhost:8000"
echo "  LANGCHAIN_SECRET=dev-shared-secret-evaltask-2026"
echo "  EVALTASK_TENANT_ID=dev-tenant"
echo "  OPENROUTER_API_KEY=sk-or-v1-votre-clé-ici"
echo "==========================================="
