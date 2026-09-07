# EvalTask — Architecture de l'intégration IA

## Vue d'ensemble

L'assistant IA d'EvalTask repose sur une architecture multi-tenant avec un serveur LangChain centralisé qui orchestre les appels LLM, et une plateforme Rails qui exécute les outils et gère les permissions.

## Composants

### 1. Rails (AssistantService)

`app/services/assistant_service.rb` — Point d'entrée côté Rails.

**Responsabilités** :
- Résolution du provider (`langchain`, `gemini`, `openai`, `anthropic`, `openrouter`)
- Génération du JWT signé avec secret partagé (`LANGCHAIN_SECRET`)
- Construction du contexte utilisateur (rôles, modules, permissions)
- Enrichissement du contexte de page (entity_type, entity_code, entity_name)
- Envoi de la requête au serveur LangChain (`POST /api/v1/chat`)
- Réception des tool_calls et exécution via `AssistantToolExecutor`
- Boucle tool calling (max 3 rounds)
- Gestion du rapport spécial (`generate_admin_report` → retour immédiat avec download_url)

**Flux `ask_langchain`** :
```
1. Préparer JWT + contexte
2. POST /api/v1/chat → serveur LangChain
3. Si tool_calls dans la réponse :
   a. Exécuter chaque tool via AssistantToolExecutor
   b. POST /api/v1/chat avec tool_results
   c. Répéter (max 3 rounds)
4. Retourner reply + tool_calls + download_url (si rapport)
```

### 2. Rails (AssistantToolExecutor)

`app/services/assistant_tool_executor.rb` — Exécuteur d'outils.

**Responsabilités** :
- Dispatch des function calls vers les méthodes `tool_*`
- Vérification des permissions Pundit pour chaque action
- Filtrage des données via `policy_scope` (l'utilisateur ne voit que ses données)
- Formatage des résultats en Hash JSON

**Outils disponibles** : 12 outils de consultation + 8 outils d'action + 1 générateur de rapport (voir `03_outils_assistant.md`)

### 3. Rails (AssistantReportExporter)

`app/services/assistant_report_exporter.rb` — Générateur de fichiers.

**Formats** :
- **HTML** : rendu HTML stylé (CSS inline, tableaux, en-têtes)
- **PDF** : Prawn (A4, marges, en-tête bleu corporate, pied de page numéroté)
- **Word** : Caracal (DOCX natif, titres, tableaux, styles)

### 4. Serveur LangChain

`/Users/ageocoly/SProcess/LangChain_Evaltask` — Serveur Python FastAPI.

**Responsabilités** :
- Authentification JWT multi-tenant (vérification du token et du tenant_id)
- Rate limiting par tenant (Redis, 120 req/min en dev)
- Orchestration LLM via OpenRouter (modèle primaire + fallback)
- RAG via ChromaDB (collections tenant-isolées + collection globale)
- Mémoire de conversation (Redis, configurable max messages)
- Tool calling : délègue l'exécution à Rails
- Corrélation via `request_id` propagé end-to-end

**Endpoint** : `POST /api/v1/chat`

**Requête** (`ChatRequest`) :
```json
{
  "message": "string | null",
  "conversation_history": [],
  "user_context": { "name", "roles", "modules", "user_id" },
  "page_context": { "entity_type", "entity_code", "entity_name", "page_title", "page_path" },
  "tenant_id": "string",
  "openrouter_api_key": "string",
  "model": "string | null",
  "session_id": "string",
  "request_id": "string | null",
  "tool_results": [{ "tool_call_id", "name", "result" }] | null
}
```

**Réponse** (`ChatResponse`) :
```json
{
  "reply": "string | null",
  "tool_calls": [{ "id", "name", "arguments" }],
  "error": "string | null",
  "model_used": "string",
  "tenant_id": "string",
  "request_id": "string",
  "duration_ms": "int | null"
}
```

## Sécurité

### Authentification
- JWT HS256 signé avec secret partagé (`LANGCHAIN_SECRET`)
- Token court-lifed (généré par requête, expiration ~5 min)
- Claims : `tenant_id`, `iat`, `exp`
- Vérification : `tenant_id` du JWT doit correspondre au `tenant_id` de la requête

### Isolation multi-tenant
- Chaque tenant a sa propre clé OpenRouter (pas de clé globale sur le serveur)
- La clé API est passée par requête, jamais persistée sur le serveur
- ChromaDB : collections isolées par tenant + collection globale partagée
- Redis : clés préfixées par `tenant_id`
- Rate limiting : par tenant, pas par IP

### Permissions
- Les outils sont exécutés côté Rails avec vérification Pundit
- L'utilisateur ne voit que les données de son périmètre (policy_scope)
- Les actions de modification requièrent une autorisation explicite (authorize_action!)
- Le contexte utilisateur (rôles, modules) est passé au LLM pour adapter le discours

## Configuration

### Rails (`.env` ou `config/initializers/ai.rb`)
```
AI_PROVIDER=langchain
LANGCHAIN_SERVER_URL=http://localhost:8000
LANGCHAIN_SECRET=dev-shared-secret-evaltask-2026
EVALTASK_TENANT_ID=dev-tenant
OPENROUTER_API_KEY=sk-or-v1-xxx
OPENROUTER_MODEL=  # vide = serveur LangChain choisit (z-ai/glm-5.2)
```

### LangChain (`.env`)
```
JWT_SECRET=dev-shared-secret-evaltask-2026
OPENROUTER_DEFAULT_MODEL=z-ai/glm-5.2
OPENROUTER_FALLBACK_MODEL=google/gemma-3-27b-it
REDIS_URL=redis://localhost:6379/0
CHROMADB_PATH=./data/chromadb
RATE_LIMIT_PER_MINUTE=120
```

### Priorité de configuration
1. `AppSetting` (base de données Rails) — priorité la plus haute
2. `Rails.application.config.x` (initializer / ENV)
3. Valeurs par défaut codées en dur

## KPIs et indicateurs

### Indicateurs projet
- `progress_actual` : avancement global (%)
- `elapsed_pct` : temps écoulé (%)
- `on_track?` : avancement ≥ temps écoulé - 5%
- `budget_variance` : budget_revised - budget_baseline
- `budget_variance_pct` : écart budgétaire relatif

### Indicateurs EVM (PeriodReport)
- CPI, SPI, CV, SV, EAC, ETC, VAC, TCPI
- Calculés via `Reporting::EvmCalculator` et `Reporting::VarianceCalculator`

### Indicateurs QSSE
- NC ouvertes / critiques / jours_open
- Incidents ouverts / jours perdus / avec arrêt
- Risques par niveau d'exposition (faible → critique)

### Indicateurs financiers
- Total facturé HT/TTC, total payé, reste à payer
- Factures en retard (count + montant)
- Coûts réels (CostEntry) vs budget
