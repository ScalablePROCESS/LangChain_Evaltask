# LangChain EvalTask Server

Serveur LangChain centralisé pour les plateformes **EvalTask** déployées en multi-tenant.

## Architecture

```
┌───────────────────────────────────────────────────────┐
│          SERVEUR LANGCHAIN CENTRALISÉ                 │
│  Python / FastAPI + LangChain + ChromaDB + Redis      │
│                                                       │
│  - RAG multi-tenant (global + par client)             │
│  - Tool calling (exécuté côté Rails)                  │
│  - Mémoire de conversation (Redis)                    │
│  - Authentification JWT par plateforme                │
└─────────────────┬─────────────────────────────────────┘
                  │ HTTPS
      ┌───────────┼───────────┐
      │           │           │
  EvalTask A  EvalTask B  EvalTask C   (KVM VPS LWS)
  Key: AAA    Key: BBB    Key: CCC     (clés OpenRouter)
```

## Prérequis

- Python 3.11+
- Redis 7+
- Docker & Docker Compose (recommandé)

## Installation

### Avec Docker (recommandé)

```bash
cp .env.example .env
# Éditer .env avec vos valeurs
docker compose up -d
```

### Sans Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Démarrer Redis séparément
# redis-server

cp .env.example .env
# Éditer .env

# Développement
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Production
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## Ingestion des connaissances globales

```bash
python scripts/ingest_global_knowledge.py
```

Ajoutez vos documents `.md` dans `data/knowledge/` puis relancez le script.

## Endpoints

| Méthode | URL | Description |
|---------|-----|-------------|
| `GET` | `/` | Info serveur |
| `GET` | `/api/v1/health` | Healthcheck (Redis, ChromaDB) |
| `POST` | `/api/v1/chat` | Chat principal (tool calling + RAG) |
| `POST` | `/api/v1/embed/text` | Ingestion de textes |
| `POST` | `/api/v1/embed/file` | Ingestion de fichiers |
| `POST` | `/api/v1/search` | Recherche vectorielle |
| `GET` | `/docs` | Documentation Swagger |
| `GET` | `/redoc` | Documentation ReDoc |

## Authentification

Chaque plateforme EvalTask signe un JWT avec le secret partagé (`JWT_SECRET`) :

```ruby
# Côté Rails (EvalTask)
payload = { tenant_id: "client_abc", iat: Time.now.to_i, exp: 5.minutes.from_now.to_i }
token = JWT.encode(payload, ENV["LANGCHAIN_SECRET"], "HS256")
```

Le token est envoyé dans le header `Authorization: Bearer <token>`.

## Configuration côté EvalTask (Rails)

Variables d'environnement à ajouter sur chaque plateforme EvalTask :

```bash
LANGCHAIN_SERVER_URL=https://langchain.evaltask.com
LANGCHAIN_SECRET=your-shared-jwt-secret
EVALTASK_TENANT_ID=client_abc
OPENROUTER_API_KEY=sk-or-v1-xxxxx
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Structure du projet

```
langchain_server/
├── app/
│   ├── main.py              # FastAPI entrypoint
│   ├── config.py             # Configuration (pydantic-settings)
│   ├── api/
│   │   ├── chat.py           # POST /api/v1/chat
│   │   ├── embed.py          # POST /api/v1/embed/*
│   │   └── health.py         # GET /api/v1/health
│   ├── auth/
│   │   └── jwt_auth.py       # Vérification JWT tenant
│   ├── chains/
│   │   └── evaltask_chain.py # Chaîne LangChain principale
│   ├── memory/
│   │   └── conversation.py   # Mémoire Redis
│   ├── tools/
│   │   └── definitions.py    # Outils EvalTask (exécutés côté Rails)
│   └── vectorstore/
│       └── manager.py        # Vectorstore multi-tenant ChromaDB
├── data/
│   └── knowledge/            # Connaissances globales BTP (.md)
├── scripts/
│   └── ingest_global_knowledge.py
├── tests/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
└── .env.example
```

## Sécurité

- Les **données métier** ne transitent jamais par ce serveur. Les outils sont exécutés côté Rails.
- Chaque tenant est **isolé** dans son propre namespace ChromaDB.
- Les **clés OpenRouter** sont propres à chaque plateforme (isolation des coûts).
- L'authentification se fait par **JWT signé** avec un secret partagé.
