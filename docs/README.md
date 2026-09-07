# Documentation — Serveur LangChain EvalTask

> **Index de la documentation** — Version 2.0 — Juillet 2026

---

## Documents disponibles

| Document | Public cible | Description |
|---|---|---|
| **[Guide d'Architecture](architecture.md)** | Tous publics | Architecture complète du projet, expliquée pour les non-spécialistes IA. Couvre les briques technologiques, le flux d'une requête, la sécurité, la fiabilité, l'observabilité et la gestion des coûts. |
| **[Guide de Démarrage Rapide](quickstart.md)** | Développeurs, intégrateurs | Installation en 5 minutes, premier appel API, intégration côté Rails, streaming SSE, tool calling, ingestion de documents, tests et dépannage. |
| **[Référence API](api_reference.md)** | Développeurs | Documentation détaillée de tous les endpoints HTTP : chat, streaming, embedding, recherche, clés API, coûts, cache, feedback, santé. |

---

## Par où commencer ?

### Je veux comprendre le projet

→ Lisez le **[Guide d'Architecture](architecture.md)**, en commençant par la
section "Vue d'ensemble" et "Le problème que résout ce projet". Le glossaire
en fin de document explique tous les termes techniques.

### Je veux installer et tester

→ Suivez le **[Guide de Démarrage Rapide](quickstart.md)**, section
"Installation en 5 minutes".

### Je veux intégrer l'API dans mon application

→ Consultez la **[Référence API](api_reference.md)** pour le détail de chaque
endpoint, et le **[Guide de Démarrage Rapide](quickstart.md)** section 4
pour un exemple d'intégration Ruby/Rails.

### Je veux comprendre le tool calling

→ Le **[Guide d'Architecture](architecture.md)** section 5.2 explique le
principe, et le **[Guide de Démarrage Rapide](quickstart.md)** section 6
montre un exemple de code.

### Je veux déployer en production

→ Le **[Guide d'Architecture](architecture.md)** section 12 couvre le
déploiement Docker, et la section 11 liste toutes les variables
d'environnement à configurer.

---

## Statistiques du projet

| Métrique | Valeur |
|---|---|
| Version | 2.0.0 |
| Tests | 110 (100% de réussite) |
| Modules Python | 42 |
| Endpoints API | 15+ |
| Outils EvalTask | 11 |
| Modèles LLM supportés | 5+ (via OpenRouter) |
| Linting | Ruff (0 erreurs) |
| CI/CD | GitHub Actions |
| Pre-commit | Ruff + hooks standards |
