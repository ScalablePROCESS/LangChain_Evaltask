# Guide d'Architecture — Serveur LangChain EvalTask

> **Document de référence technique** — Version 2.0 — Juillet 2026

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Le problème que résout ce projet](#2-le-problème-que-résout-ce-projet)
3. [Architecture générale](#3-architecture-générale)
4. [Les briques technologiques expliquées](#4-les-briques-technologiques-expliquées)
5. [Le flux d'une requête : du message utilisateur à la réponse](#5-le-flux-dune-requête-du-message-utilisateur-à-la-réponse)
6. [Sécurité et isolation multi-tenant](#6-sécurité-et-isolation-multi-tenant)
7. [Fiabilité et résilience](#7-fiabilité-et-résilience)
8. [Observabilité et monitoring](#8-observabilité-et-monitoring)
9. [Gestion des coûts LLM](#9-gestion-des-coûts-llm)
10. [Structure détaillée du code](#10-structure-détaillée-du-code)
11. [Configuration et variables d'environnement](#11-configuration-et-variables-denvironnement)
12. [Déploiement](#12-déploiement)
13. [Glossaire](#13-glossaire)

---

## 1. Vue d'ensemble

Le **Serveur LangChain EvalTask** est un service backend centralisé qui apporte
des capacités d'intelligence artificielle (IA) aux plateformes **EvalTask** —
des applications web de gestion de projets BTP (Bâtiment, Travaux Publics).

En termes simples : **c'est un "cerveau IA" partagé** qui comprend les questions
des utilisateurs d'EvalTask, cherche des informations dans une base de
connaissances, demande aux plateformes EvalTask d'exécuter des actions
(récupérer des données, générer des rapports), puis formule une réponse
intelligente en langage naturel.

### Caractéristiques principales

| Caractéristique | Description |
|---|---|
| **Multi-tenant** | Un seul serveur sert plusieurs plateformes EvalTask clientes, avec isolation totale des données |
| **RAG** | Retrieval-Augmented Generation — l'IA s'appuie sur une base de connaissances documentaire |
| **Tool calling** | L'IA peut demander à la plateforme EvalTask d'exécuter des actions (lister des projets, générer un rapport, etc.) |
| **Streaming** | Les réponses peuvent être diffusées en temps réel (Server-Sent Events) pour une expérience utilisateur fluide |
| **Fiabilité** | Fallback automatique entre modèles d'IA, circuit breaker, cache de réponses |
| **Observabilité** | Métriques Prometheus, logs structurés, suivi des coûts par tenant |

---

## 2. Le problème que résout ce projet

### Sans ce serveur

Chaque plateforme EvalTask devrait :
- Intégrer son propre moteur IA (coût de développement élevé)
- Gérer individuellement les appels aux modèles d'IA (OpenRouter, OpenAI, etc.)
- Maintenir sa propre base de connaissances vectorielle
- Implémenter la logique de tool calling, cache, fiabilité, etc.

### Avec ce serveur

- **Un seul serveur central** gère toute la logique IA
- Chaque plateforme EvalTask n'a qu'à envoyer un message + un token JWT
- Le serveur fait tout le reste : RAG, tool calling, fallback, cache, coûts
- Les **données métier restent côté EvalTask** — le serveur IA ne les stocke jamais

```
┌─────────────────────────────────────────────────────┐
│              SERVEUR LANGCHAIN CENTRALISÉ            │
│                                                      │
│  "Cerveau IA" partagé par toutes les plateformes     │
│  - Comprend les questions                           │
│  - Cherche dans la base de connaissances (RAG)       │
│  - Demande des actions aux plateformes (tools)       │
│  - Formule des réponses intelligentes                │
│                                                      │
│  Python / FastAPI + LangChain + ChromaDB + Redis     │
└───────────┬───────────────┬───────────────┬─────────┘
            │               │               │
     ┌──────┴──────┐ ┌──────┴──────┐ ┌──────┴──────┐
     │  EvalTask A  │ │  EvalTask B  │ │  EvalTask C  │
     │  (Client A)  │ │  (Client B)  │ │  (Client C)  │
     │  Clé: AAA    │ │  Clé: BBB    │ │  Clé: CCC    │
     └──────────────┘ └──────────────┘ └──────────────┘
        Plateforme       Plateforme       Plateforme
        Rails/BTP        Rails/BTP        Rails/BTP
```

---

## 3. Architecture générale

### Les 4 grands blocs

```
┌──────────────────────────────────────────────────────────────────┐
│                        API FASTAPI                                │
│  /api/v1/chat  ·  /api/v1/chat/stream  ·  /api/v1/embed/*        │
│  /api/v1/keys  ·  /api/v1/costs  ·  /api/v1/feedback             │
│  /api/v1/health  ·  /api/v1/ready  ·  /metrics                    │
├──────────────────────────────────────────────────────────────────┤
│                     CHAÎNE LANGCHAIN                              │
│                                                                    │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐     │
│  │ Détection   │  │ Construction │  │   Appel LLM          │     │
│  │ d'intention │→│ des messages │→│   (OpenRouter)        │     │
│  │ (cache?)    │  │ (RAG + ctx)  │  │   + fallback modèle  │     │
│  └─────────────┘  └──────────────┘  └──────────┬───────────┘     │
│                                                  │                 │
│                                       ┌──────────┴───────────┐   │
│                                       │  Tool calls ?        │   │
│                                       │  Oui → retour client │   │
│                                       │  Non → réponse texte │   │
│                                       └──────────────────────┘   │
├──────────────────────────────────────────────────────────────────┤
│                    INFRASTRUCTURE                                 │
│                                                                    │
│  ┌──────────┐  ┌──────────────┐  ┌───────────┐  ┌──────────┐    │
│  │  Redis   │  │   ChromaDB   │  │ Circuit   │  │  Cost    │    │
│  │  Cache   │  │   Vectoriel  │  │ Breaker   │  │ Tracker  │    │
│  │  Mémoire │  │   (RAG)      │  │           │  │          │    │
│  └──────────┘  └──────────────┘  └───────────┘  └──────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

### Composants et leurs rôles

| Composant | Technologie | Rôle |
|---|---|---|
| **API** | FastAPI (Python) | Point d'entrée HTTP, validation, authentification |
| **Chaîne IA** | LangChain | Orchestration du LLM, RAG, tool calling |
| **LLM** | OpenRouter (z-ai/glm-5.2, gpt-4o-mini) | Génération de texte, compréhension, tool calling |
| **Base vectorielle** | ChromaDB | Stockage et recherche de documents (RAG) |
| **Cache & mémoire** | Redis | Cache de réponses, mémoire de conversation, rate limiting |
| **Circuit breaker** | Python (interne) | Protection contre les pannes d'OpenRouter |
| **Suivi des coûts** | Redis + Python | Tracking des tokens et coûts par tenant |
| **Métriques** | Prometheus (interne) | Monitoring des performances et de la santé |

---

## 4. Les briques technologiques expliquées

### 4.1 FastAPI — L'API web

**Pour un non-technicien :** FastAPI est comme un "réceptionniste" qui reçoit les
requêtes HTTP, vérifie que tout est en ordre (authentification, validation des
données), puis transmet au bon service.

**Points clés :**
- Endpoints REST documentés automatiquement (Swagger UI sur `/docs`)
- Validation des données entrantes avec Pydantic (types stricts)
- Support du streaming SSE (Server-Sent Events) pour les réponses en temps réel
- Middleware pour la corrélation (request_id) et les métriques

### 4.2 LangChain — L'orchestrateur IA

**Pour un non-technicien :** LangChain est le "chef d'orchestre" qui coordonne
tous les éléments : il prépare le contexte, interroge le modèle d'IA, gère les
appels d'outils, et formule la réponse finale.

**Dans ce projet, LangChain est utilisé pour :**
- Construire les messages envoyés au LLM (system prompt + contexte + historique)
- Gérer le tool calling (le LLM demande des actions, on les renvoie au client)
- Supporter le streaming (réponse mot par mot)
- Faire le lien entre la base de connaissances vectorielle et le LLM

### 4.3 OpenRouter — Le fournisseur de modèles IA

**Pour un non-technicien :** OpenRouter est comme un "routeur d'IA" — au lieu
d'être lié à un seul modèle (ChatGPT, Claude, Gemini...), on peut bascululer
entre plusieurs modèles via une seule API.

**Configuration :**
- **Modèle principal :** `z-ai/glm-5.2` (économique, performant en français)
- **Modèle de fallback :** `openai/gpt-4o-mini` (si le principal est en panne)
- Chaque tenant peut utiliser sa propre clé API OpenRouter (isolation des coûts)

### 4.4 ChromaDB — La base de connaissances vectorielle

**Pour un non-technicien :** ChromaDB est une "bibliothèque intelligente". Au
lieu de chercher par mots-clés exacts, elle cherche par **sens** (proximité
sémantique). Par exemple, si on cherche "budget", elle trouvera aussi des
documents qui parlent de "coûts" ou "dépenses".

**Comment ça marche :**
1. Les documents sont découpés en petits morceaux (chunks)
2. Chaque chunk est transformé en vecteur (une liste de nombres) par un modèle
   d'embedding (`sentence-transformers/all-MiniLM-L6-v2`)
3. Quand l'utilisateur pose une question, sa question est aussi transformée en vecteur
4. ChromaDB trouve les chunks les plus "proches" (sémantiquement) de la question
5. Ces chunks sont ajoutés au contexte envoyé au LLM

**Isolation multi-tenant :**
- Une collection `evaltask_global` contient les connaissances BTP partagées
- Chaque tenant a sa propre collection `evaltask_{tenant_id}`
- Les recherches interrogent les deux collections (global + tenant)

### 4.5 Redis — Le couteau suisse

**Pour un non-technicien :** Redis est une base de données ultra-rapide qui
sert à plusieurs choses dans ce projet :

| Usage | Description |
|---|---|
| **Cache de réponses** | Si deux utilisateurs posent la même question, la deuxième réponse vient du cache (pas de rappel LLM) |
| **Mémoire de conversation** | L'historique des échanges est stocké pour garder le contexte |
| **Rate limiting** | Limite le nombre de requêtes par tenant (anti-abus) |
| **Stockage des clés API** | Les clés OpenRouter sont stockées chiffrées (Fernet) |
| **Suivi des coûts** | Compteurs de tokens et coûts par tenant |
| **Cache des résumés** | Les résumés de conversation sont mis en cache pour éviter de les régénérer |

### 4.6 Circuit Breaker — Le disjoncteur

**Pour un non-technicien :** Le circuit breaker est comme un "disjoncteur
électrique". Si OpenRouter (le fournisseur d'IA) tombe en panne, au lieu
d'attendre 60 secondes à chaque requête, le circuit "saute" et les requêtes
échouent immédiatement. Après un délai, il essaie à nouveau (half-open).

**Les trois états :**
```
CLOSED (normal) ──échecs──→ OPEN (tout échoue immédiatement)
                                  │
                              cooldown (30s)
                                  ↓
                             HALF_OPEN (1 test)
                                  │
                          succès? │ échec?
                         ┌────────┴────────┐
                         ↓                 ↓
                    CLOSED            OPEN
```

---

## 5. Le flux d'une requête : du message utilisateur à la réponse

### 5.1 Flux simplifié (chat non-streaming)

```
Utilisateur pose une question sur EvalTask
         │
         ↓
Plateforme Rails envoie POST /api/v1/chat
  { message: "Quel est le budget du projet PRJ-001 ?",
    tenant_id: "client_abc",
    user_context: { name: "Alice", roles: ["pm_direction"] } }
         │
         ↓
┌─── Serveur LangChain ──────────────────────────────┐
│                                                     │
│  1. Authentification JWT                            │
│     "Ce token est-il valide ? Ce tenant existe-t-il ?" │
│                                                     │
│  2. Détection d'intention                           │
│     "Bonjour" → réponse directe (pas d'appel LLM)   │
│     "Quel est le budget..." → nécessite le LLM      │
│                                                     │
│  3. Cache lookup                                    │
│     "Cette question a-t-elle déjà été posée         │
│      récemment par ce tenant ?"                     │
│     Oui → retour immédiat depuis le cache           │
│                                                     │
│  4. Construction du contexte                        │
│     a. Détection de langue (français, anglais...)   │
│     b. Récupération RAG (ChromaDB)                  │
│        "Quels documents sont pertinents ?"          │
│     c. Construction du system prompt                │
│        (rôle utilisateur + contexte métier + RAG)   │
│     d. Résumé de conversation si historique long    │
│     e. Vérification du budget (coûts LLM)           │
│     f. Vérification du circuit breaker              │
│                                                     │
│  5. Appel au LLM (OpenRouter)                       │
│     Modèle principal: z-ai/glm-5.2                  │
│     Si échec → fallback: openai/gpt-4o-mini         │
│                                                     │
│  6. Analyse de la réponse                           │
│     a. Le LLM veut-il utiliser un outil ?           │
│        (tool_calls dans la réponse)                 │
│     b. Si oui → renvoyer les tool_calls au client   │
│     c. Si non → c'est une réponse texte finale      │
│                                                     │
│  7. Post-traitement                                 │
│     a. Détection d'anomalies dans les données       │
│        (CPI < 0.9, tâches en retard, etc.)          │
│     b. Mise en cache de la réponse                  │
│     c. Enregistrement des coûts (tokens utilisés)   │
│     d. Métriques Prometheus                         │
│                                                     │
└─────────────────────────────────────────────────────┘
         │
         ↓
Réponse renvoyée à Rails
  { reply: "Le budget du projet PRJ-001 est de 15M FCFA...",
    model_used: "z-ai/glm-5.2",
    duration_ms: 1234 }
```

### 5.2 Flux avec tool calling (multi-tours)

Le tool calling est un dialogue en plusieurs étapes :

```
Tour 1:
  Utilisateur: "Quel est le budget du projet PRJ-001 ?"
  Serveur IA → LLM → "J'ai besoin de l'outil get_project_details"
  Réponse: { tool_calls: [{ name: "get_project_details",
                             arguments: { project_code: "PRJ-001" } }] }

Tour 2 (Rails exécute l'outil localement):
  Rails envoie: { tool_results: [{ tool_call_id: "...",
                                    name: "get_project_details",
                                    result: { budget: 15000000, ... } }] }
  Serveur IA → LLM (avec les résultats) → "Le budget est de 15M FCFA..."
  Réponse: { reply: "Le budget du projet PRJ-001 est de 15 000 000 FCFA..." }
```

**Pourquoi les outils sont exécutés côté Rails ?**
> Les données métier (projets, budgets, stocks...) ne transitent **jamais**
> par le serveur IA. C'est la plateforme EvalTask qui exécute les outils
> localement et renvoie uniquement les résultats. Cela garantit la
> confidentialité et la sécurité des données clients.

### 5.3 Flux streaming (SSE)

Le streaming permet d'afficher la réponse mot par mot au lieu d'attendre
la réponse complète :

```
POST /api/v1/chat/stream

data: {"type": "token", "content": "Le"}\n\n
data: {"type": "token", "content": " budget"}\n\n
data: {"type": "token", "content": " du"}\n\n
data: {"type": "token", "content": " projet"}\n\n
...
data: {"type": "done", "model_used": "z-ai/glm-5.2", "duration_ms": 1234}\n\n
```

Si le LLM décide d'utiliser des outils pendant le stream, les tool_calls
sont détectés dans les chunks et envoyés immédiatement :

```
data: {"type": "tool_calls", "tool_calls": [...]}\n\n
```

---

## 6. Sécurité et isolation multi-tenant

### 6.1 Authentification JWT

Chaque plateforme EvalTask signe un token JWT avec un secret partagé :

```ruby
# Côté Rails (EvalTask)
payload = { tenant_id: "client_abc", iat: Time.now.to_i, exp: 5.minutes.from_now.to_i }
token = JWT.encode(payload, ENV["LANGCHAIN_SECRET"], "HS256")
```

Le serveur vérifie :
- La signature du token (secret partagé)
- La non-expiration du token
- La correspondance entre `tenant_id` du token et celui de la requête

### 6.2 Validation de sécurité au démarrage

En production (`DEBUG=false`), le serveur refuse de démarrer si :
- `JWT_SECRET` est la valeur par défaut (`change-me-in-production`)
- `JWT_SECRET` fait moins de 32 bytes (recommandation RFC 7518)
- `ALLOWED_ORIGINS` est `*` (CORS sauvage interdit en production)

### 6.3 Isolation des données

| Couche | Mécanisme d'isolation |
|---|---|
| **ChromaDB** | Collections séparées par tenant (`evaltask_{tenant_id}`) |
| **Redis** | Préfixe de clé par tenant (`evaltask:cost:{tenant_id}:*`) |
| **Clés API** | Chiffrées avec Fernet, isolées par tenant dans Redis |
| **Rate limiting** | Compteurs séparés par tenant |
| **Coûts** | Tracking indépendant par tenant avec budget configurable |

### 6.4 Rate limiting

Le rate limiting protège contre les abus. Il est configurable :

| Paramètre | Défaut | Description |
|---|---|---|
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | 30 | Requêtes chat par minute par tenant |
| `RATE_LIMIT_EMBED_PER_MINUTE` | 10 | Ingestions de documents par minute |
| `RATE_LIMIT_FAIL_OPEN` | true | Si Redis est en panne : `true` = laisser passer, `false` = bloquer (503) |

### 6.5 Chiffrement des clés API

Les clés OpenRouter sont stockées chiffrées dans Redis (chiffrement Fernet,
dérivé du `JWT_SECRET` via SHA-256). Elles ne transitent jamais en clair
dans les logs.

---

## 7. Fiabilité et résilience

### 7.1 Fallback de modèle

Si le modèle principal (`z-ai/glm-5.2`) est indisponible, le serveur bascule
automatiquement vers le modèle de fallback (`openai/gpt-4o-mini`). Ce
fonctionnement s'applique tant en mode non-streaming qu'en streaming.

### 7.2 Circuit breaker

Le circuit breaker protège contre les pannes prolongées d'OpenRouter :
- **5 échecs consécutifs** → circuit OPEN (échec immédiat, pas d'attente)
- **30 secondes de cooldown** → circuit HALF_OPEN (un test)
- **Test réussi** → circuit CLOSED (retour à la normale)

### 7.3 Cache de réponses

Les réponses textuelles (sans tool_calls) sont mises en cache dans Redis
pendant 10 minutes (configurable). Une question identique dans ce délai
retourne la réponse en cache sans appel LLM — réduisant les coûts et la latence.

### 7.4 Résumé de conversation

Quand l'historique dépasse 10 messages (configurable), un résumé est généré
par le LLM et mis en cache. Les 4 derniers messages sont conservés intacts.
Cela évite d'envoyer un historique trop long au LLM (coût + limite de tokens).

### 7.5 Détection d'anomalies

Le serveur analyse les résultats d'outils pour détecter des anomalies
critiques et les signaler proactivement à l'utilisateur :

| Anomalie | Seuil | Description |
|---|---|---|
| CPI < 0.9 | Dépassement budgétaire | Cost Performance Index — le projet coûte plus que prévu |
| SPI < 0.9 | Retard planning | Schedule Performance Index — le projet prend du retard |
| Tâches en retard | Critique | Tâches dont la date de fin prévue est dépassée |
| Incidents QSSE | Non traités | Incidents de sécurité non résolus depuis trop longtemps |

### 7.6 Fallback usage_metadata en streaming

Certains fournisseurs LLM ne renvoient pas les métadonnées d'usage (tokens
consommés) dans les chunks de streaming. Le serveur estime alors les tokens
à partir de la longueur du contenu généré (~4 caractères par token) pour
maintenir un suivi des coûts fiable.

---

## 8. Observabilité et monitoring

### 8.1 Métriques Prometheus

Le serveur expose des métriques au format Prometheus sur `/metrics` :

| Métrique | Type | Description |
|---|---|---|
| `evaltask_http_requests_total` | Counter | Requêtes HTTP (par méthode, path, status) |
| `evaltask_http_request_duration_seconds` | Histogram | Durée des requêtes HTTP (buckets Prometheus) |
| `evaltask_llm_calls_total` | Counter | Appels LLM (par tenant, modèle, status) |
| `evaltask_llm_duration_seconds` | Histogram | Durée des appels LLM |
| `evaltask_llm_cost_usd_total` | Counter | Coût LLM cumulé par tenant |
| `evaltask_cache_hits_total` | Counter | Hits de cache par tenant |
| `evaltask_cache_misses_total` | Counter | Miss de cache par tenant |
| `evaltask_circuit_breaker_state` | Gauge | État du circuit breaker |
| `evaltask_active_conversations` | Gauge | Conversations actives |

Les histogrammes utilisent des buckets Prometheus standard :
`0.005s, 0.01s, 0.025s, 0.05s, 0.1s, 0.25s, 0.5s, 1s, 2.5s, 5s, 10s, +Inf`

### 8.2 Logs structurés

- Format configurable : `text` (lisible) ou `json` (pour ELK/Datadog)
- Champs sensibles masqués (`openrouter_api_key`, `jwt_secret`, `embedding_api_key`)
- Corrélation via `request_id` (UUID généré ou fourni par le client)

### 8.3 Endpoints de santé

| Endpoint | Type | Description |
|---|---|---|
| `GET /api/v1/health` | Liveness | Le serveur répond-il ? |
| `GET /api/v1/ready` | Readiness | Redis et ChromaDB sont-ils disponibles ? (200 ou 503) |
| `GET /metrics` | Prometheus | Métriques au format texte |
| `GET /api/v1/circuit-breaker` | Diagnostic | État du circuit breaker |
| `GET /api/v1/redis/pool` | Diagnostic | Infos sur le pool Redis |

---

## 9. Gestion des coûts LLM

### 9.1 Principe

Chaque appel au LLM consomme des tokens (unités de texte facturées par
OpenRouter). Le serveur track ces tokens pour chaque tenant :

```
evaltask:cost:{tenant_id}:current  → { total_tokens, total_cost_usd, ... }
evaltask:cost:{tenant_id}:daily:{date} → compteurs par jour
evaltask:cost:{tenant_id}:log → derniers 100 appels (détail)
```

### 9.2 Budget par tenant

Chaque tenant a un budget configurable (défaut : $50 USD). Avant chaque
appel LLM, le serveur vérifie si le budget est dépassé. Si oui, la requête
est rejetée avec un message d'erreur.

### 9.3 Tarifs des modèles

| Modèle | Prompt ($/1M tokens) | Completion ($/1M tokens) |
|---|---|---|
| `z-ai/glm-5.2` | $0.50 | $1.50 |
| `openai/gpt-4o-mini` | $0.15 | $0.60 |
| `openai/gpt-4o` | $2.50 | $10.00 |
| `anthropic/claude-3.5-sonnet` | $3.00 | $15.00 |
| `google/gemini-2.0-flash` | $0.10 | $0.40 |

---

## 10. Structure détaillée du code

```
langchain_evaltask/
├── app/
│   ├── main.py                    # Point d'entrée FastAPI, middleware, routes
│   ├── config.py                  # Configuration centralisée (pydantic-settings)
│   ├── redis_pool.py              # Pool de connexions Redis (singleton)
│   │
│   ├── api/                       # Endpoints HTTP
│   │   ├── chat.py                #   POST /api/v1/chat + /chat/stream (SSE)
│   │   ├── embed.py               #   POST /api/v1/embed/text + /embed/file
│   │   ├── health.py              #   GET /api/v1/health + /ready
│   │   ├── keys.py                #   POST /api/v1/keys (gestion clés API)
│   │   ├── costs.py               #   GET /api/v1/costs (suivi coûts)
│   │   ├── cache.py               #   DELETE /api/v1/cache (invalidation)
│   │   └── feedback.py            #   POST /api/v1/feedback (thumbs up/down)
│   │
│   ├── auth/                      # Sécurité
│   │   ├── jwt_auth.py            #   Vérification JWT, rate limiting, audit
│   │   └── api_key_manager.py     #   Stockage chiffré des clés OpenRouter
│   │
│   ├── chains/                    # Logique IA
│   │   └── evaltask_chain.py      #   Chaîne LangChain principale (invoke + astream)
│   │
│   ├── conversation/              # Gestion de conversation
│   │   ├── intent_detector.py     #   Détection d'intention (salutations, aide...)
│   │   ├── language_detector.py   #   Détection de langue (fr, en, ar...)
│   │   ├── summarizer.py          #   Résumé automatique d'historique
│   │   └── anomaly_detector.py    #   Détection d'anomalies dans les données
│   │
│   ├── tools/                     # Définitions d'outils
│   │   └── definitions.py         #   11 outils EvalTask (exécutés côté Rails)
│   │
│   ├── vectorstore/               # Base de connaissances (RAG)
│   │   ├── manager.py             #   Gestionnaire ChromaDB multi-tenant
│   │   └── reranker.py            #   Reranker de résultats (Cross-Encoder)
│   │
│   ├── memory/                    # Mémoire de conversation
│   │   └── conversation.py        #   Stockage Redis par tenant + session
│   │
│   ├── cache/                     # Cache de réponses
│   │   └── response_cache.py      #   Cache Redis avec métriques Prometheus
│   │
│   ├── cost/                      # Suivi des coûts
│   │   └── tracker.py             #   CostTracker par tenant (Redis)
│   │
│   ├── feedback/                  # Retours utilisateurs
│   │   └── store.py               #   Stockage des thumbs up/down (Redis)
│   │
│   ├── document/                  # Traitement de documents
│   │   ├── adaptive_splitter.py   #   Découpage Markdown adaptatif
│   │   └── extractor.py           #   Extraction texte (PDF, DOCX, TXT, MD)
│   │
│   └── observability/             # Monitoring
│       ├── metrics.py             #   Métriques Prometheus (counters, gauges, histograms)
│       ├── circuit_breaker.py     #   Circuit breaker OpenRouter
│       └── logging_config.py      #   Configuration des logs
│
├── data/
│   ├── chromadb/                  # Persistance ChromaDB (vectoriel)
│   └── knowledge/                 # Documents de connaissances globales BTP (.md)
│
├── scripts/
│   └── ingest_global_knowledge.py # Script d'ingestion des connaissances globales
│
├── tests/                         # 110 tests (auth, cache, costs, chain, etc.)
├── docs/                          # Documentation
├── .github/workflows/ci.yml       # Pipeline CI (lint + test)
├── .pre-commit-config.yaml        # Hooks pre-commit (ruff, format)
├── Dockerfile                     # Image Docker
├── docker-compose.yml             # Orchestration (serveur + Redis)
├── pyproject.toml                 # Configuration Python (ruff, pytest)
├── requirements.txt               # Dépendances
└── .env.example                   # Template de configuration
```

### Les 11 outils EvalTask

Ces outils sont définis côté serveur IA mais **exécutés côté plateforme EvalTask** :

| Outil | Description | Paramètres clés |
|---|---|---|
| `list_projects` | Liste les projets accessibles | `status`, `project_type`, `search` |
| `get_project_details` | Détails complets d'un projet | `project_code` (requis) |
| `get_project_dashboard` | Tableau de bord synthétique | `project_code` (requis) |
| `list_tasks` | Tâches d'un projet ou assignées | `project_code`, `status`, `assigned_to_me` |
| `get_cost_summary` | Résumé des coûts (budget, écarts) | `project_code` (requis) |
| `list_purchase_orders` | Bons de commande | `project_code`, `status`, `supplier` |
| `list_incidents` | Incidents QSSE | `project_code`, `severity`, `status` |
| `get_stock_levels` | Niveaux de stock + alertes | `warehouse`, `search`, `below_threshold` |
| `get_financial_summary` | Résumé financier | `period`, `project_code` |
| `generate_admin_report` | Rapport exportable (PDF/Word) | `report_type` (requis), `format`, `export_format` |
| `search_data` | Recherche transversale | `query` (requis), `scope` |

---

## 11. Configuration et variables d'environnement

Toute la configuration se fait via des variables d'environnement (fichier `.env`).
Voir `.env.example` pour le template complet.

### Variables essentielles

| Variable | Défaut | Description |
|---|---|---|
| `JWT_SECRET` | (à définir) | Secret partagé pour les tokens JWT (min 32 bytes en production) |
| `OPENROUTER_DEFAULT_MODEL` | `z-ai/glm-5.2` | Modèle LLM principal |
| `OPENROUTER_FALLBACK_MODEL` | `openai/gpt-4o-mini` | Modèle de secours |
| `REDIS_URL` | `redis://localhost:6379/0` | URL de connexion Redis |
| `CHROMA_PERSIST_DIR` | `./data/chromadb` | Répertoire de persistance ChromaDB |
| `DEBUG` | `false` | Mode debug (relaxe certaines validations de sécurité) |
| `ALLOWED_ORIGINS` | `*` | Origines CORS autorisées (liste explicite en production) |

### Variables de performance

| Variable | Défaut | Description |
|---|---|---|
| `REDIS_MAX_CONNECTIONS` | 20 | Taille du pool Redis |
| `CACHE_ENABLED` | true | Active le cache de réponses |
| `CACHE_TTL_SECONDS` | 600 | Durée de vie du cache (10 min) |
| `MAX_TOOL_ROUNDS` | 5 | Nombre maximum d'allers-retours tool calling |
| `SUMMARY_THRESHOLD_MESSAGES` | 10 | Seuil de résumé d'historique |

---

## 12. Déploiement

### 12.1 Avec Docker (recommandé)

```bash
cp .env.example .env
# Éditer .env avec vos valeurs (JWT_SECRET, ALLOWED_ORIGINS, etc.)
docker compose up -d
```

Le `docker-compose.yml` démarre :
- Le serveur LangChain (port 8000)
- Redis (port 6379)
- Un healthcheck sur `/api/v1/ready`

### 12.2 Sans Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Démarrer Redis séparément
redis-server

cp .env.example .env
# Éditer .env

# Développement
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Production
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 12.3 Ingestion des connaissances globales

```bash
python scripts/ingest_global_knowledge.py
```

Ajoutez vos documents `.md` dans `data/knowledge/` puis relancez le script.
Ces documents seront indexés dans la collection `evaltask_global` de ChromaDB
et partagés avec tous les tenants.

### 12.4 CI/CD

Le pipeline GitHub Actions (`.github/workflows/ci.yml`) exécute sur chaque
push/PR :
1. **Lint** : `ruff check` + `ruff format --check`
2. **Test** : `pytest tests/ -v`

Les hooks pre-commit (`.pre-commit-config.yaml`) appliquent automatiquement
ruff et vérifient la qualité du code avant chaque commit.

---

## 13. Glossaire

| Terme | Définition simple |
|---|---|
| **LLM** | Large Language Model — un modèle d'IA qui comprend et génère du texte (ex: ChatGPT, Claude) |
| **RAG** | Retrieval-Augmented Generation — technique qui consiste à chercher des documents pertinents avant de générer une réponse |
| **Embedding** | Transformation d'un texte en vecteur (liste de nombres) pour permettre la recherche sémantique |
| **Vectoriel** | Qui utilise des vecteurs pour représenter le sens des textes et mesurer leur proximité |
| **Token** | Unité de texte facturée par les modèles d'IA (~4 caractères ou ~0.75 mot) |
| **Tool calling** | Capacité du LLM à demander l'exécution d'une fonction externe (ex: récupérer des données) |
| **Streaming** | Envoi de la réponse au fur et à mesure de sa génération (mot par mot) |
| **SSE** | Server-Sent Events — protocole HTTP pour le streaming temps réel |
| **JWT** | JSON Web Token — token d'authentification signé cryptographiquement |
| **Tenant** | Client/plateforme utilisant le serveur (ex: "client_abc" = une entreprise EvalTask) |
| **Circuit breaker** | Disjoncteur qui protège contre les pannes d'un service externe |
| **Fallback** | Solution de secours (ex: modèle de secours si le principal est en panne) |
| **ChromaDB** | Base de données vectorielle open-source pour le RAG |
| **Redis** | Base de données en mémoire ultra-rapide (cache, mémoire, rate limiting) |
| **OpenRouter** | Service qui donne accès à plusieurs modèles d'IA via une seule API |
| **CPI** | Cost Performance Index — rapport entre le budget prévu et réalisé (1.0 = conforme) |
| **SPI** | Schedule Performance Index — rapport entre l'avancement prévu et réel (1.0 = conforme) |
| **QSSE** | Qualité, Sécurité, Santé, Environnement — normes BTP |
| **Singleton** | Pattern de conception où une seule instance d'un objet existe dans toute l'application |
