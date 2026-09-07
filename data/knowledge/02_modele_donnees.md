# EvalTask — Modèle de données

## Vue d'ensemble

La plateforme EvalTask repose sur 62 modèles ActiveRecord et 65 tables PostgreSQL. Le schéma est organisé autour de l'entité centrale **Project**, avec une structure hiérarchique Project → Phase → WorkPackage → Task.

## Hiérarchie projet

```
Project
├── ProjectPhase (phase : études, terrassement, gros œuvre, second œuvre, finitions…)
│   ├── WorkPackage (lot : zone, lot, sous-lot — hiérarchie arborescente)
│   │   ├── Task (tâche : unité d'exécution avec avancement)
│   │   ├── BoqItem (ligne de BOQ : quantités, prix, rendements)
│   │   ├── CostEntry (saisie de coût imputée)
│   │   └── PeriodReportLine (ligne de reporting périodique EVM)
│   └── ScheduleBaseline (baseline de planning)
├── CostBaseline (baseline budgétaire)
├── PeriodReport (rapport périodique : EVM, écarts coût/délai)
├── PurchaseRequest → PurchaseOrder → DeliveryNote → Invoice
├── QualityNonconformity
├── SafetyIncident
├── RiskRegisterItem
├── ChangeOrder (avenant, ordre de service)
└── Document
```

## Entités principales

### Project

Le projet est l'entité centrale. Il porte le budget, l'avancement, les dates et le statut global.

| Champ | Type | Description |
|---|---|---|
| `code` | string | Code unique (ex: PRJ-2026-001) |
| `name` | string | Nom du projet |
| `project_status` | enum | preparation, appel_offres, execution, suspended, reception_provisoire, reception_definitive, completed, cancelled |
| `project_type` | enum | batiment_residentiel, batiment_commercial, batiment_industriel, infrastructure_routiere, ouvrage_art, hydraulique, vrd, equipement_public, amenagement_urbain, energie_renouvelable |
| `contract_type` | enum | forfait, unit_price, cost_plus, mixte |
| `budget_baseline` | decimal | Budget initial (baseline) |
| `budget_revised` | decimal | Budget révisé (après avenants) |
| `progress_actual` | integer | Avancement global 0-100% (calculé depuis les phases) |
| `starts_on` | date | Date de début |
| `ends_on` | date | Date de fin |
| `city`, `region` | string | Localisation |
| `manager_id` | FK User | Chef de projet |
| `organization_id` | FK Organization | Maître d'ouvrage |

**Méthodes calculées** : `budget_variance`, `budget_variance_pct`, `duration_days`, `elapsed_pct`, `on_track?` (avancement ≥ temps écoulé - 5%).

### ProjectPhase

Phase du projet (études, terrassement, gros œuvre, etc.). L'avancement est pondéré par `weight`.

| Champ | Type | Description |
|---|---|---|
| `code` | string | Code unique dans le projet |
| `name` | string | Nom de la phase |
| `status` | enum | a_venir, en_cours, terminee, annulee |
| `weight` | decimal | Pondération pour calcul avancement (0-100) |
| `planned_start/end` | date | Dates planifiées |
| `actual_start/end` | date | Dates réelles |
| `progress_actual` | integer | Avancement 0-100% (calculé depuis les lots) |

### WorkPackage

Lot de travaux (hiérarchie zone → lot → sous-lot). L'avancement est pondéré par `planned_quantity` ou moyenne simple.

| Champ | Type | Description |
|---|---|---|
| `code` | string | Code unique dans le projet |
| `name` | string | Nom du lot |
| `level` | enum | zone, lot, sous_lot |
| `status` | enum | actif, suspendu, termine, annule |
| `parent_id` | FK | Lot parent (hiérarchie) |
| `budget_planned` | decimal | Budget planifié du lot |
| `budget_revised` | decimal | Budget révisé |
| `progress_actual` | integer | Avancement 0-100% (calculé depuis les tâches) |
| `responsible_id` | FK User | Responsable du lot |

### Task

Unité d'exécution élémentaire. L'avancement remonte vers WorkPackage → ProjectPhase → Project.

| Champ | Type | Description |
|---|---|---|
| `code` | string | Code unique (ex: PRJ-2026-001-T001) |
| `name` | string | Nom de la tâche |
| `status` | enum | a_faire, en_cours, en_controle, terminee, bloquee, annulee |
| `priority` | enum | basse, normale, haute, critique |
| `progress_pct` | integer | Avancement 0-100% |
| `planned_start/end` | date | Dates planifiées |
| `actual_start/end` | date | Dates réelles |
| `planned_quantity` | decimal | Quantité planifiée |
| `actual_quantity` | decimal | Quantité réalisée |
| `planned_duration_days` | integer | Durée planifiée |
| `assigned_to_id` | FK User | Assigné à |
| `is_critical_path` | boolean | Tâche sur chemin critique |
| `predecessor_ids` | array | Tâches antérieures |

**Propagation** : `after_save` → `WorkPackage.recalculate_progress!` → `ProjectPhase.recalculate_progress!` → `Project.recalculate_progress!`

### BoqItem (Ligne de BOQ)

Ligne du Bordereau des Prix Unitaires. Lie les quantités planifiées/réalisées aux coûts imputés.

| Champ | Type | Description |
|---|---|---|
| `code` | string | Code de la ligne |
| `description` | string | Description |
| `unit` | string | Unité (m, m², m³, t, h, forfait…) |
| `quantity_planned` | decimal | Quantité planifiée |
| `quantity_realized` | decimal | Quantité réalisée |
| `unit_price_planned` | decimal | Prix unitaire planifié |
| `unit_price_actual` | decimal | Prix unitaire réel |
| `yield_planned/actual` | decimal | Rendement planifié/réel |
| `total_planned` | decimal | Total planifié (auto-calculé) |
| `charged_cost` | decimal | Coût imputé via CostEntry |
| `cost_variance` | decimal | Écart budget vs coût réel |

### CostEntry

Saisie de coût imputée à un projet et optionnellement à un lot/tâche/BOQ.

| Champ | Type | Description |
|---|---|---|
| `entry_date` | date | Date de saisie |
| `category` | enum | main_oeuvre, materiau, equipement, sous_traitance, transport, location, etudes_controle, frais_generaux, divers |
| `description` | string | Description |
| `amount` | decimal | Montant |
| `quantity` | decimal | Quantité |
| `unit_cost` | decimal | Coût unitaire |
| `source_type` | enum | manual, actual_entry, invoice, stock_movement |
| `auto_generated` | boolean | Saisie automatique (depuis facture, mouvement de stock…) |
| `project_id` | FK Project | Projet |
| `work_package_id` | FK WorkPackage | Lot (optionnel) |
| `boq_item_id` | FK BoqItem | Ligne BOQ (optionnel) |
| `task_id` | FK Task | Tâche (optionnelle) |
| `invoice_id` | FK Invoice | Facture source (si auto) |

## Cycle achats

### PurchaseRequest (Demande d'achat)

| Champ | Type | Description |
|---|---|---|
| `code` | string | Code unique (ex: DA-2026-001) |
| `status` | enum | brouillon, soumise, approuvee, rejetee, commandee, annulee |
| `urgency` | enum | normale, urgente, critique |
| `justification` | text | Justification |
| `needed_by` | date | Date de besoin |
| `estimated_total` | decimal | Total estimé (depuis les lignes) |
| `requested_by_id` | FK User | Demandeur |
| `approved_by_id` | FK User | Approbateur |

**Workflow** : brouillon → soumise → approuvee/rejetee → commandee. Transitions atomiques avec `with_lock`.

### PurchaseOrder (Bon de commande)

| Champ | Type | Description |
|---|---|---|
| `code` | string | Code unique |
| `status` | enum | brouillon, envoye, confirme, partiellement_livre, livre, cloture, annule |
| `supplier_id` | FK Supplier | Fournisseur |
| `total_ht/ttc` | decimal | Totaux |
| `expected_delivery_date` | date | Date de livraison prévue |

### Invoice (Facture)

| Champ | Type | Description |
|---|---|---|
| `code` | string | Code unique |
| `invoice_type` | enum | fournisseur, avoir_fournisseur, client, avoir_client |
| `status` | enum | brouillon, validee, comptabilisee, payee_partiellement, payee, annulee |
| `total_ht/tva/ttc` | decimal | Totaux (auto-calculés depuis les lignes) |
| `amount_paid` | decimal | Montant payé |
| `invoice_date` | date | Date de facture |
| `due_date` | date | Date d'échéance |
| `overdue?` | method | `due_date < today ET status ∉ [payee, annulee]` |

**Validation** : `validate_invoice!` → déclenche `CostIntegrationService.from_invoice` (génère CostEntry auto).

## QSSE

### QualityNonconformity (Non-conformité)

| Champ | Type | Description |
|---|---|---|
| `code` | string | Code unique (ex: NC-2026-001) |
| `severity` | enum | mineure, majeure, critique |
| `status` | enum | ouverte, analyse, action_corrective, verifiee, cloturee |
| `title` | string | Titre |
| `description` | text | Description |
| `location` | string | Localisation sur chantier |
| `detected_at` | datetime | Date de détection |
| `rework_cost` | decimal | Coût de reprise |
| `detected_by_id` | FK User | Détecté par |
| `assigned_to_id` | FK User | Assigné à |

**Workflow** : ouverte → analyse → action_corrective → verifiee → cloturee. Méthode `advance!`.

### SafetyIncident (Incident de sécurité)

| Champ | Type | Description |
|---|---|---|
| `code` | string | Code unique (ex: IS-2026-001) |
| `incident_type` | enum | accident_avec_arret, accident_sans_arret, presquaccident, observation, action_preventive |
| `severity` | enum | faible, moderee, grave, critique |
| `status` | enum | signale, en_analyse, action_en_cours, cloture |
| `days_lost` | integer | Jours perdus (arrêt de travail) |
| `occurred_at` | datetime | Date de survenance |
| `with_work_stoppage?` | method | `incident_type == "accident_avec_arret"` |

**Workflow** : signale → en_analyse → action_en_cours → cloture. Méthode `advance!`.

### RiskRegisterItem (Risque)

| Champ | Type | Description |
|---|---|---|
| `code` | string | Code unique |
| `risk_category` | enum | technique, financier, planning, securite, reglementaire, meteo, fournisseur, autre |
| `probability` | integer | 1-5 |
| `impact` | integer | 1-5 |
| `exposure` | integer | probability × impact (auto-calculé) |
| `response_strategy` | enum | eviter, reduire, transferer, accepter |
| `status` | enum | identifie, en_traitement, resolu, accepte, cloture |
| `residual_probability/impact` | integer | Risque résiduel après mitigation |

**Niveaux d'exposition** : 1-5 faible, 6-12 modéré, 13-19 élevé, 20-25 critique.

## ChangeOrder (Avenant / Ordre de service)

| Champ | Type | Description |
|---|---|---|
| `code` | string | Code unique |
| `change_type` | enum | avenant_client, ordre_service, modification_interne, reclamation |
| `status` | enum | brouillon, soumis, en_analyse, approuve, rejete, applique |
| `impact_cost` | decimal | Impact financier |
| `impact_delay_days` | integer | Impact sur les délais (jours) |

## Stock

### StockArticle

| Champ | Type | Description |
|---|---|---|
| `sku` | string | Référence unique |
| `name` | string | Nom |
| `category` | enum | consommable, materiel, epi, outillage, piece_rechange, divers |
| `unit` | string | Unité |
| `valuation_method` | enum | cump, fifo |
| `min_threshold` | decimal | Seuil minimum (réappro) |
| `safety_stock` | decimal | Stock de sécurité |

### StockLevel (Niveau par entrepôt)

| Champ | Type | Description |
|---|---|---|
| `warehouse_id` | FK Warehouse | Entrepôt |
| `quantity_on_hand` | decimal | Quantité physique |
| `quantity_available` | decimal | Quantité disponible (on_hand - réservée) |

### StockMovement (Mouvement de stock)

Types : entrée, sortie, transfert, inventaire. Génère des CostEntry automatiquement pour les sorties.

## Reporting

### PeriodReport (Rapport périodique)

| Champ | Type | Description |
|---|---|---|
| `period_start/end` | date | Période couverte |
| `status` | enum | brouillon, soumis, revise, valide, publie, verrouille |
| `validated_by_id` | FK User | Validé par |
| `validated_at` | datetime | Date de validation |

### PeriodReportLine (Ligne de reporting EVM)

| Champ | Type | Description |
|---|---|---|
| `budget_baseline` | decimal | Budget initial |
| `budget_revised` | decimal | Budget révisé |
| `committed` | decimal | Engagé |
| `actual_spent` | decimal | Dépensé réel (CR) |
| `etc` | decimal | Estimate To Complete |
| `eac` | decimal | Estimate At Completion |
| `variance` | decimal | Écart (budget - EAC) |
| `cost_performance_index` | decimal | CPI (EV/AC) |

## Comptabilité

### JournalEntry / JournalEntryLine

Écritures comptables avec double entrée. Chaque ligne a : compte, débit, crédit, libellé.

### AccountingPeriod

Période comptable (exercice). Peut être clôturée (verrouillée).

## Notifications

### Notification

| Champ | Type | Description |
|---|---|---|
| `notification_type` | enum | stock_alert, da_pending, report_validated, incident_created, po_approved, nc_opened, info, warning, success |
| `severity` | enum | info, warning, danger, success |
| `read` | boolean | Lu / non lu |
| `user_id` | FK User | Destinataire |

Diffusion temps réel via `NotificationsChannel` (ActionCable).
