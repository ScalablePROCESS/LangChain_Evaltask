# EvalTask — Présentation de la plateforme

## Identité

EvalTask est une solution digitale intégrée de gestion de projets du Bâtiment et des Travaux Publics (BTP). Conçue pour les entreprises de construction, de génie civil et d'infrastructure, elle couvre l'ensemble du cycle de vie d'un projet : de la préparation à la réception définitive.

## Vision métier

La plateforme adresse les enjeux majeurs du secteur BTP :

- **Pilotage par les coûts** : maîtrise budgétaire rigoureuse avec baseline, suivi des écarts, analyse EVM (Earned Value Management)
- **Respect des délais** : planification par phases et lots de travaux, diagramme de Gantt, propagation automatique de l'avancement
- **Maîtrise des risques QSSE** : gestion des non-conformités qualité, incidents de sécurité, registre des risques
- **Traçabilité achats** : cycle complet DA → BC → BL → facture, évaluation fournisseurs
- **Conformité financière** : comptabilité intégrée avec écritures automatiques, FEC, balance, grand livre, lettrage

## Architecture technique

| Couche | Technologie |
|---|---|
| Backend | Ruby on Rails 8.0, PostgreSQL 16 |
| Frontend | Vite + Bootstrap 5 (Silva) + Stimulus.js |
| Auth | Devise + Pundit (RBAC multi-rôles) + JWT (API v1) |
| Cache/Jobs/RT | Solid Cache, Solid Queue, Solid Cable (ActionCable) |
| PDF | Prawn + prawn-table (8 services), Caracal (Word) |
| PWA | manifest.webmanifest + Workbox service worker |
| IA | Assistant IA multi-provider (LangChain centralisé) |
| Deploy | Docker + Kamal |

## Modules fonctionnels (12 activables)

1. **core_projects** — Projets, phases, lots de travaux, BOQ
2. **planning** — Tâches, planning, diagramme de Gantt, ressources
3. **costs** — Coûts, budgets, baselines, EVM, écarts
4. **purchasing** — Demandes d'achat, bons de commande, livraisons
5. **stock** — Entrepôts, articles, mouvements, inventaires, FIFO/CUMP
6. **accounting** — Factures, écritures, journaux, FEC, balance, lettrage
7. **qsse** — Non-conformités, incidents sécurité, registre des risques
8. **reporting** — Rapports périodiques, tableaux de bord, KPIs, exports
9. **resources** — Ressources, affectations, capacités, surcharge
10. **admin** — Utilisateurs, rôles, modules, paramètres, numérotation
11. **documents** — Documents, templates, pièces jointes
12. **notifications** — Notifications in-app temps réel (ActionCable)

## Rôles utilisateurs (12)

| Rôle | Code | Périmètre |
|---|---|---|
| Administrateur | `admin` | Accès complet à toutes les fonctionnalités |
| Direction de projet | `pm_direction` | Pilotage global, tableaux de bord, reporting stratégique |
| Responsable MOE | `moe_manager` | Gestion technique, exécution, Gantt, BOQ |
| Conducteur de travaux | `conducteur_travaux` | Suivi chantier, saisie réalisations, pointage |
| Responsable achats | `resp_achats` | DA, BC, livraisons, fournisseurs |
| Responsable stock | `resp_stock` | Entrepôts, articles, mouvements, inventaires |
| Comptable | `comptable` | Factures, écritures, journaux, rapprochement |
| Contrôleur de gestion | `controleur_gestion` | Analyse coûts, reporting financier, écarts |
| Chargé QSSE | `charge_qsse` | Non-conformités, incidents, registre des risques |
| Chef de chantier | `chef_chantier` | Suivi quotidien, tâches terrain, pointage |
| Ouvrier | `ouvrier` | Consultation tâches, saisie avancement, signalements |
| Client externe | `client_externe` | Consultation avancement, rapports, documents |

Un utilisateur peut cumuler plusieurs rôles (système multi-rôles via tables `roles` + `user_roles`).

## Assistant IA

La plateforme intègre un assistant IA (EvalTask AI) qui :
- Répond aux questions des utilisateurs sur les données de la plateforme
- Exécute des actions (création de DA, signalement d'incidents, mise à jour d'avancement)
- Génère des rapports professionnels (PDF, Word, HTML)
- Utilise le tool calling pour interroger les données réelles
- Respecte strictement les permissions Pundit par rôle
- S'appuie sur un serveur LangChain centralisé pour l'orchestration LLM
