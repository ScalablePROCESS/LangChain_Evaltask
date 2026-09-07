# Guide de Démarrage Rapide — Serveur LangChain EvalTask

> **Pour développeurs et intégrateurs** — Version 2.0 — Juillet 2026

---

## Table des matières

1. [Prérequis](#1-prérequis)
2. [Installation en 5 minutes](#2-installation-en-5-minutes)
3. [Premier appel à l'API](#3-premier-appel-à-lapi)
4. [Intégration côté plateforme EvalTask (Rails)](#4-intégration-côté-plateforme-evaltask-rails)
5. [Streaming SSE](#5-streaming-sse)
6. [Tool calling (multi-tours)](#6-tool-calling-multi-tours)
7. [Ingestion de documents](#7-ingestion-de-documents)
8. [Gestion des clés API](#8-gestion-des-clés-api)
9. [Tests et développement](#9-tests-et-développement)
10. [Dépannage](#10-dépannage)

---

## 1. Prérequis

| Prérequis | Version minimum | Vérification |
|---|---|---|
| Python | 3.11+ | `python --version` |
| Redis | 7+ | `redis-cli --version` |
| Docker | 24+ | `docker --version` |
| Docker Compose | 2+ | `docker compose version` |

Vous avez également besoin d'une clé API **OpenRouter** (gratuite à l'inscription
sur https://openrouter.ai).

---

## 2. Installation en 5 minutes

### Option A : Docker (recommandé)

```bash
# 1. Cloner le projet
git clone <repo-url> langchain_evaltask
cd langchain_evaltask

# 2. Copier la configuration
cp .env.example .env

# 3. Éditer .env — au minimum :
#    JWT_SECRET=<votre-secret-de-32-caracteres-minimum>
#    ALLOWED_ORIGINS=https://votre-plateforme.evaltask.com
#    OPENROUTER_DEFAULT_MODEL=z-ai/glm-5.2

# 4. Démarrer
docker compose up -d

# 5. Vérifier
curl http://localhost:8000/api/v1/health
# → {"status": "ok", "server": "ok", ...}
```

### Option B : Installation locale

```bash
# 1. Cloner et créer un environnement virtuel
git clone <repo-url> langchain_evaltask
cd langchain_evaltask
python -m venv .venv
source .venv/bin/activate

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Configuration
cp .env.example .env
# Éditer .env (voir ci-dessus)

# 4. Démarrer Redis (dans un autre terminal)
redis-server

# 5. Démarrer le serveur
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 6. Vérifier
curl http://localhost:8000/api/v1/health
```

---

## 3. Premier appel à l'API

### 3.1 Générer un token JWT

Le serveur requiert un token JWT pour tous les endpoints (sauf `/` et `/health`).

```python
import jwt
import time

payload = {
    "tenant_id": "test-tenant",
    "iat": int(time.time()),
    "exp": int(time.time()) + 300,  # 5 minutes
}
token = jwt.encode(payload, "votre-jwt-secret", algorithm="HS256")
print(f"Bearer {token}")
```

### 3.2 Envoyer un message de chat

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer <votre-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Bonjour, que peux-tu faire ?",
    "tenant_id": "test-tenant",
    "openrouter_api_key": "sk-or-v1-votre-cle"
  }'
```

**Réponse attendue :**

```json
{
  "reply": "Bonjour ! Je suis l'assistant EvalTask. Je peux vous aider avec...",
  "tool_calls": [],
  "error": null,
  "model_used": "z-ai/glm-5.2",
  "tenant_id": "test-tenant",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "duration_ms": 234
}
```

> **Note :** Le message "Bonjour" est détecté comme une salutation et répond
> directement sans appel LLM (détection d'intention). Essayez avec une question
> métier pour déclencher le LLM.

### 3.3 Documentation interactive

Ouvrez votre navigateur sur :
- **Swagger UI :** http://localhost:8000/docs
- **ReDoc :** http://localhost:8000/redoc

---

## 4. Intégration côté plateforme EvalTask (Rails)

### 4.1 Configuration

Ajoutez ces variables d'environnement sur votre plateforme EvalTask :

```bash
LANGCHAIN_SERVER_URL=https://langchain.evaltask.com
LANGCHAIN_SECRET=votre-jwt-secret-partage
EVALTASK_TENANT_ID=client_abc
OPENROUTER_API_KEY=sk-or-v1-xxxxx
```

### 4.2 Code Ruby (exemple)

```ruby
# app/services/langchain_client.rb
require 'net/http'
require 'jwt'
require 'json'

class LangchainClient
  def initialize
    @url = ENV['LANGCHAIN_SERVER_URL']
    @secret = ENV['LANGCHAIN_SECRET']
    @tenant_id = ENV['EVALTASK_TENANT_ID']
  end

  def chat(message, user_context: {}, history: [], tool_results: nil)
    token = generate_jwt
    uri = URI("#{@url}/api/v1/chat")

    request = Net::HTTP::Post.new(uri)
    request['Authorization'] = "Bearer #{token}"
    request['Content-Type'] = 'application/json'
    request.body = {
      message: message,
      tenant_id: @tenant_id,
      user_context: user_context,
      conversation_history: history,
      tool_results: tool_results,
      openrouter_api_key: ENV['OPENROUTER_API_KEY']
    }.to_json

    response = Net::HTTP.start(uri.hostname, uri.port, use_ssl: uri.scheme == 'https') do |http|
      http.request(request)
    end

    JSON.parse(response.body)
  end

  private

  def generate_jwt
    payload = {
      tenant_id: @tenant_id,
      iat: Time.now.to_i,
      exp: 5.minutes.from_now.to_i
    }
    JWT.encode(payload, @secret, 'HS256')
  end
end
```

### 4.3 Gestion des tool_calls

Quand la réponse contient `tool_calls`, votre plateforme doit exécuter les
outils localement et renvoyer les résultats :

```ruby
# Exemple : gestion d'un tool_call
result = langchain.chat("Quel est le budget du projet PRJ-001 ?")

if result['tool_calls'].any?
  tool_results = result['tool_calls'].map do |tc|
    # Exécuter l'outil localement
    case tc['name']
    when 'get_project_details'
      project = Project.find_by(code: tc['arguments']['project_code'])
      { tool_call_id: tc['id'], name: tc['name'], result: project.as_json }
    end
  end

  # Renvoyer les résultats pour le tour suivant
  final_result = langchain.chat(nil, tool_results: tool_results)
  puts final_result['reply']
end
```

---

## 5. Streaming SSE

Le streaming permet d'afficher la réponse en temps réel :

```python
import httpx
import jwt
import time
import json

token = jwt.encode(
    {"tenant_id": "test-tenant", "iat": int(time.time()), "exp": int(time.time()) + 300},
    "votre-jwt-secret",
    algorithm="HS256",
)

with httpx.stream(
    "POST",
    "http://localhost:8000/api/v1/chat/stream",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    json={"message": "Analyse le budget du projet PRJ-001", "tenant_id": "test-tenant"},
) as response:
    for line in response.iter_lines():
        if line.startswith("data: "):
            event = json.loads(line[6:])
            if event["type"] == "token":
                print(event["content"], end="", flush=True)
            elif event["type"] == "tool_calls":
                print(f"\n[Outils demandés: {event['tool_calls']}]")
            elif event["type"] == "done":
                print(f"\n[Terminé en {event['duration_ms']}ms avec {event['model_used']}]")
            elif event["type"] == "error":
                print(f"\n[Erreur: {event['error']}]")
```

---

## 6. Tool calling (multi-tours)

Le tool calling est un dialogue en plusieurs étapes entre le serveur IA et
votre plateforme :

```
┌──────────┐         ┌──────────┐         ┌──────────┐
│  Client   │         │ Serveur   │         │   LLM    │
│ (Rails)   │         │  LangCh.  │         │(OpenRout)│
└─────┬─────┘         └─────┬─────┘         └─────┬─────┘
      │                     │                     │
      │ POST /chat          │                     │
      │ "Budget PRJ-001?"   │                     │
      ├────────────────────>│                     │
      │                     │ ainvoke()           │
      │                     ├────────────────────>│
      │                     │                     │
      │                     │ tool_calls:         │
      │                     │ get_project_details │
      │                     │<────────────────────┤
      │                     │                     │
      │ { tool_calls: [...] }│                    │
      │<────────────────────┤                     │
      │                     │                     │
      │ Exécuter l'outil    │                     │
      │ localement          │                     │
      │                     │                     │
      │ POST /chat          │                     │
      │ { tool_results: [...]}│                   │
      ├────────────────────>│                     │
      │                     │ ainvoke()           │
      │                     ├────────────────────>│
      │                     │                     │
      │                     │ "Le budget est..."  │
      │                     │<────────────────────┤
      │                     │                     │
      │ { reply: "Le..." }  │                     │
      │<────────────────────┤                     │
```

**Maximum 5 tours** (`MAX_TOOL_ROUNDS=5`) pour éviter les boucles infinies.

---

## 7. Ingestion de documents

### 7.1 Connaissances globales (partagées entre tous les tenants)

```bash
# Placer vos documents .md dans data/knowledge/
cp ~/Documents/guide_btp.md data/knowledge/
cp ~/Documents/normes_qsse.md data/knowledge/

# Ingérer
python scripts/ingest_global_knowledge.py
```

### 7.2 Documents spécifiques à un tenant (via API)

```bash
# Ingestion de texte
curl -X POST http://localhost:8000/api/v1/embed/text \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "client_abc",
    "texts": ["Le projet PRJ-001 a un budget de 15M FCFA..."],
    "source": "note_interne"
  }'

# Ingestion de fichier
curl -X POST http://localhost:8000/api/v1/embed/file \
  -H "Authorization: Bearer <token>" \
  -F "tenant_id=client_abc" \
  -F "file=@document.pdf"
```

Formats supportés : PDF, DOCX, TXT, MD.

---

## 8. Gestion des clés API

### 8.1 Stocker une clé côté serveur (recommandé)

Au lieu d'envoyer la clé OpenRouter dans chaque requête, stockez-la une fois :

```bash
curl -X POST http://localhost:8000/api/v1/keys \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "client_abc",
    "api_key": "sk-or-v1-xxxxx"
  }'
```

La clé est **chiffrée** (Fernet) et stockée dans Redis. Les requêtes
suivantes n'ont plus besoin de `openrouter_api_key`.

### 8.2 Supprimer une clé

```bash
curl -X DELETE http://localhost:8000/api/v1/keys \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "client_abc"}'
```

---

## 9. Tests et développement

### 9.1 Lancer les tests

```bash
# Installer les dépendances de dev
pip install -e ".[dev]"

# Lancer tous les tests
pytest

# Avec verbosité
pytest tests/ -v --tb=short

# Un fichier spécifique
pytest tests/test_chat.py -v
```

### 9.2 Linting et formatage

```bash
# Vérifier le code
ruff check app/ tests/

# Formater
ruff format app/ tests/

# Pre-commit (installe les hooks git)
pip install pre-commit
pre-commit install
```

### 9.3 CI/CD

Le pipeline GitHub Actions (`.github/workflows/ci.yml`) s'exécute sur chaque
push/PR vers `main` ou `develop` :

- **Job lint** : `ruff check` + `ruff format --check`
- **Job test** : `pytest tests/ -v`

---

## 10. Dépannage

### Le serveur refuse de démarrer

```
ValueError: JWT_SECRET doit être défini en production (debug=False)
```

**Solution :** Définir `JWT_SECRET` avec une valeur de au moins 32 caractères
dans `.env`, ou mettre `DEBUG=true` pour le développement.

```
ValueError: ALLOWED_ORIGINS='*' est interdit en production (debug=False)
```

**Solution :** Spécifier les origines explicites : `ALLOWED_ORIGINS=https://client-a.evaltask.com,https://client-b.evaltask.com`

### Erreur 401 — Unauthorized

**Cause :** Token JWT manquant, expiré, ou signé avec le mauvais secret.

**Solution :** Vérifier que `JWT_SECRET` correspond entre le serveur LangChain
et la plateforme EvalTask. Vérifier que le token n'est pas expiré.

### Erreur 429 — Too Many Requests

**Cause :** Rate limit dépassé (30 req/min par défaut).

**Solution :** Attendre 60 secondes (voir l'en-tête `Retry-After` dans la
réponse) ou augmenter `RATE_LIMIT_REQUESTS_PER_MINUTE`.

### Erreur 503 — Service Unavailable

**Cause :** Circuit breaker ouvert (OpenRouter en panne) ou Redis indisponible.

**Solution :** Vérifier l'état du circuit breaker :
```bash
curl http://localhost:8000/api/v1/circuit-breaker
```
Vérifier Redis :
```bash
redis-cli ping
# → PONG
```

### Pas de réponse du LLM (timeout)

**Cause :** OpenRouter indisponible ou modèle trop lent.

**Solution :** Le fallback modèle devrait prendre le relais automatiquement.
Vérifier les logs pour voir si le fallback a été déclenché. Le circuit breaker
devrait s'ouvrir après 5 échecs consécutifs.

### ChromaDB vide (pas de RAG)

**Solution :** Ingérer des documents :
```bash
python scripts/ingest_global_knowledge.py
```

### Les coûts ne sont pas trackés en streaming

**Cause :** Certains fournisseurs ne renvoient pas `usage_metadata` dans les
chunks de streaming.

**Note :** Le serveur estime les tokens à partir de la longueur du contenu
(~4 chars/token) en fallback. Vérifier les logs pour confirmer.
