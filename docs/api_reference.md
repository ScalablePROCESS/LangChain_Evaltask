# Référence API — Serveur LangChain EvalTask

> **Documentation technique des endpoints** — Version 2.0 — Juillet 2026

---

## Table des matières

1. [Authentification](#authentification)
2. [Chat](#chat)
3. [Embedding / Ingestion](#embedding--ingestion)
4. [Recherche vectorielle](#recherche-vectorielle)
5. [Gestion des clés API](#gestion-des-clés-api)
6. [Coûts](#coûts)
7. [Cache](#cache)
8. [Feedback](#feedback)
9. [Santé et monitoring](#santé-et-monitoring)

---

## Authentification

Tous les endpoints (sauf `/` et `/api/v1/health`) requièrent un token JWT
dans l'en-tête `Authorization: Bearer <token>`.

### Format du token JWT

```json
{
  "tenant_id": "client_abc",
  "iat": 1722300000,
  "exp": 1722300300
}
```

| Champ | Type | Description |
|---|---|---|
| `tenant_id` | string | Identifiant du tenant (doit correspondre à la requête) |
| `iat` | int | Issued At — timestamp d'émission |
| `exp` | int | Expiration — timestamp (recommandé : +5 minutes) |

### Codes d'erreur

| Code | Cause | Solution |
|---|---|---|
| **401** | Token manquant, expiré ou invalide | Régénérer le token |
| **403** | `tenant_id` du token ≠ `tenant_id` de la requête | Vérifier la cohérence |
| **422** | Message ou `tool_results` manquant | Fournir au moins un des deux |
| **429** | Rate limit dépassé | Attendre (voir `Retry-After`) |
| **503** | Service indisponible (circuit breaker, Redis) | Réessayer plus tard |

---

## Chat

### POST /api/v1/chat

Chat IA non-streaming avec tool calling et RAG.

#### Requête

```json
{
  "message": "Quel est le budget du projet PRJ-001 ?",
  "tenant_id": "client_abc",
  "conversation_history": [
    {"role": "user", "content": "Bonjour"},
    {"role": "assistant", "content": "Bonjour ! Comment puis-je vous aider ?"}
  ],
  "user_context": {
    "name": "Alice Dupont",
    "roles": ["pm_direction"],
    "modules": ["projects", "costs"],
    "user_id": "user-123"
  },
  "page_context": {
    "entity_type": "project",
    "entity_code": "PRJ-001",
    "entity_name": "Construction Centre Ville",
    "page_title": "Projet PRJ-001",
    "page_path": "/projects/PRJ-001"
  },
  "openrouter_api_key": "sk-or-v1-xxxxx",
  "model": "z-ai/glm-5.2",
  "session_id": "sess-abc123",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "tool_results": null
}
```

| Champ | Type | Requis | Description |
|---|---|---|---|
| `message` | string \| null | Oui* | Message utilisateur (*ou `tool_results`) |
| `tenant_id` | string | Oui | Doit correspondre au JWT |
| `conversation_history` | list[dict] | Non | Historique (`{role, content}`), max 30 messages |
| `user_context` | object | Non | Contexte utilisateur (nom, rôles, modules) |
| `page_context` | object | Non | Contexte de la page courante |
| `openrouter_api_key` | string | Non | Clé OpenRouter (optionnel si stockée côté serveur) |
| `model` | string | Non | Modèle LLM (défaut: `openrouter_default_model`) |
| `session_id` | string | Non | Session de mémoire (défaut: `"default"`) |
| `request_id` | string | Non | Corrélation (auto-généré si absent) |
| `tool_results` | list[ToolResult] | Non | Résultats d'outils (tour de tool calling) |

#### Réponse

```json
{
  "reply": "Le budget du projet PRJ-001 est de 15 000 000 FCFA...",
  "tool_calls": [],
  "error": null,
  "model_used": "z-ai/glm-5.2",
  "tenant_id": "client_abc",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "duration_ms": 1234
}
```

| Champ | Type | Description |
|---|---|---|
| `reply` | string \| null | Réponse texte (null si `tool_calls` non vide) |
| `tool_calls` | list[ToolCallOut] | Outils à exécuter côté Rails |
| `error` | string \| null | Message d'erreur |
| `model_used` | string | Modèle réellement utilisé (peut différer en cas de fallback) |
| `tenant_id` | string | Identifiant du tenant |
| `request_id` | string | Identifiant de corrélation |
| `duration_ms` | int | Durée de traitement (ms) |

#### ToolCallOut

```json
{
  "id": "call_abc123",
  "name": "get_project_details",
  "arguments": {"project_code": "PRJ-001"}
}
```

#### ToolResult (pour le tour suivant)

```json
{
  "tool_call_id": "call_abc123",
  "name": "get_project_details",
  "result": {"budget": 15000000, "status": "execution", ...}
}
```

---

### POST /api/v1/chat/stream

Chat IA en streaming Server-Sent Events (SSE).

#### Format des événements

```
data: {"type": "token", "content": "Le"}\n\n
data: {"type": "token", "content": " budget"}\n\n
...
data: {"type": "tool_calls", "tool_calls": [...]}\n\n
...
data: {"type": "done", "model_used": "z-ai/glm-5.2", "duration_ms": 1234, "full_reply": "..."}\n\n
```

| Type | Champs | Description |
|---|---|---|
| `token` | `content` | Fragment de texte généré |
| `tool_calls` | `tool_calls` | Outils à exécuter (stream interrompu) |
| `done` | `model_used`, `duration_ms`, `full_reply` | Fin du stream |
| `error` | `error` | Erreur pendant le stream |

#### Headers de la réponse

```
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

---

## Embedding / Ingestion

### POST /api/v1/embed/text

Ingestion de textes bruts dans la base vectorielle du tenant.

#### Requête

```json
{
  "tenant_id": "client_abc",
  "texts": ["Le projet PRJ-001 a un budget de 15M FCFA..."],
  "source": "note_interne",
  "metadatas": [{"category": "finance"}],
  "scope": "tenant",
  "openrouter_api_key": "sk-or-v1-xxxxx"
}
```

| Champ | Type | Requis | Description |
|---|---|---|---|
| `tenant_id` | string | Oui | Identifiant du tenant |
| `texts` | list[string] | Oui | Textes à ingérer |
| `source` | string | Non | Source des documents |
| `metadatas` | list[dict] | Non | Métadonnées par texte |
| `scope` | string | Non | `"tenant"` (défaut) ou `"global"` |
| `openrouter_api_key` | string | Non | Clé OpenRouter (pour embeddings) |

#### Réponse

```json
{
  "status": "ok",
  "documents_ingested": 1,
  "chunks_created": 3,
  "tenant_id": "client_abc"
}
```

---

### POST /api/v1/embed/file

Ingestion d'un fichier (PDF, DOCX, TXT, MD).

#### Requête (multipart/form-data)

| Champ | Type | Requis | Description |
|---|---|---|---|
| `tenant_id` | string | Oui | Identifiant du tenant |
| `file` | file | Oui | Fichier à ingérer |
| `source` | string | Non | Nom de la source |
| `scope` | string | Non | `"tenant"` ou `"global"` |

#### Formats supportés

| Extension | Format |
|---|---|
| `.pdf` | PDF (PyMuPDF) |
| `.docx` | Word (python-docx) |
| `.txt` | Texte brut |
| `.md` | Markdown |

---

## Recherche vectorielle

### POST /api/v1/search

Recherche sémantique dans la base vectorielle.

#### Requête

```json
{
  "tenant_id": "client_abc",
  "query": "budget construction",
  "top_k": 5,
  "scope": "both"
}
```

| Champ | Type | Requis | Description |
|---|---|---|---|
| `tenant_id` | string | Oui | Identifiant du tenant |
| `query` | string | Oui | Requête de recherche |
| `top_k` | int | Non | Nombre de résultats (défaut: 5) |
| `scope` | string | Non | `"tenant"`, `"global"`, ou `"both"` (défaut) |

---

## Gestion des clés API

### POST /api/v1/keys

Stocke (ou met à jour) la clé API OpenRouter d'un tenant (chiffrée Fernet).

```json
{
  "tenant_id": "client_abc",
  "api_key": "sk-or-v1-xxxxx"
}
```

### GET /api/v1/keys/{tenant_id}

Vérifie si une clé est stockée pour ce tenant (ne retourne pas la clé elle-même).

### DELETE /api/v1/keys

Supprime la clé API d'un tenant.

```json
{
  "tenant_id": "client_abc"
}
```

---

## Coûts

### GET /api/v1/costs/{tenant_id}

Récupère le suivi des coûts LLM pour un tenant.

#### Réponse

```json
{
  "tenant_id": "client_abc",
  "current": {
    "total_tokens": 125000,
    "prompt_tokens": 80000,
    "completion_tokens": 45000,
    "total_cost_usd": 0.1875,
    "budget_usd": 50.0,
    "budget_exceeded": false
  },
  "daily": {
    "2026-07-29": {
      "tokens": 12000,
      "cost_usd": 0.018
    }
  }
}
```

### POST /api/v1/costs/{tenant_id}/budget

Définit un budget personnalisé pour un tenant.

```json
{
  "budget_usd": 100.0
}
```

---

## Cache

### DELETE /api/v1/cache

Invalide le cache de réponses pour un tenant.

```json
{
  "tenant_id": "client_abc"
}
```

### GET /api/v1/cache/stats

Statistiques du cache (hits, misses, taille).

---

## Feedback

### POST /api/v1/feedback

Enregistre un retour utilisateur (thumbs up/down).

```json
{
  "tenant_id": "client_abc",
  "user_id": "user-123",
  "request_id": "550e8400-...",
  "rating": "up",
  "comment": "Réponse très précise"
}
```

| Champ | Type | Requis | Description |
|---|---|---|---|
| `tenant_id` | string | Oui | Identifiant du tenant |
| `user_id` | string | Non | Utilisateur |
| `request_id` | string | Non | Requête concernée |
| `rating` | string | Oui | `"up"` ou `"down"` |
| `comment` | string | Non | Commentaire optionnel |

### GET /api/v1/feedback/{tenant_id}/stats

Statistiques de feedback pour un tenant.

---

## Santé et monitoring

### GET /

Info serveur (version, status, liens docs).

### GET /api/v1/health

Healthcheck liveness — le serveur répond-il ?

```json
{
  "status": "ok",
  "server": "ok",
  "timestamp": "2026-07-29T23:30:00Z"
}
```

### GET /api/v1/ready

Readiness probe — Redis et ChromaDB sont-ils disponibles ?

```json
{
  "ready": true,
  "checks": {
    "redis": "ok",
    "chromadb": "ok"
  }
}
```

Retourne **503** si une dépendance est indisponible.

### GET /metrics

Métriques au format Prometheus (texte).

### GET /api/v1/circuit-breaker

État du circuit breaker OpenRouter.

```json
{
  "state": "closed",
  "failure_count": 0,
  "failure_threshold": 5,
  "cooldown_seconds": 30,
  "last_failure_at": null
}
```

### GET /api/v1/redis/pool

Infos sur le pool de connexions Redis.

```json
{
  "created_connections": 5,
  "available_connections": 3,
  "max_connections": 20
}
```
