# EvalTask — Processus métier BTP

## Cycle de vie d'un projet

```
préparation → appel_offres → execution → [suspended] → reception_provisoire → reception_definitive → completed
                                                                                                  ↘ cancelled
```

### 1. Préparation
- Création du projet (code, nom, type, budget baseline, dates)
- Définition du contrat (forfait, unit_price, cost_plus, mixte)
- Découpage en phases (études, terrassement, gros œuvre, second œuvre, finitions)
- Création des lots de travaux (WorkPackage : zone → lot → sous-lot)
- Établissement du BOQ (Bordereau des Prix Unitaires)
- Planification des tâches (dates, durées, quantités, antériorités)

### 2. Exécution
- Saisie de l'avancement des tâches (progress_pct, actual_quantity)
- Propagation automatique : Task → WorkPackage → ProjectPhase → Project
- Saisie des coûts réels (CostEntry : main d'œuvre, matériel, équipement, sous-traitance)
- Cycle achats : DA → BC → BL → Facture → CostEntry auto
- Suivi QSSE : signalements NC et incidents, registre des risques
- Reporting périodique : EVM, écarts coût/délai, KPIs

### 3. Réception
- Réception provisoire (à la fin des travaux)
- Levée des réserves (non-conformités à corriger)
- Réception définitive (après période de garantie)

## Cycle achats (Purchase workflow)

```
Demande d'achat (DA)                Bon de commande (BC)           Livraison (BL)           Facture
┌──────────────┐                   ┌──────────────┐              ┌──────────────┐         ┌──────────────┐
│  brouillon   │                   │   brouillon   │              │              │         │   brouillon   │
│     ↓        │                   │     ↓        │              │              │         │     ↓        │
│   soumise    │─── approbation ──→│    envoye     │── livraison │   reçue      │── fact │   validee    │
│     ↓        │                   │     ↓        │              │              │         │     ↓        │
│  approuvee   │                   │    confirme   │              │              │         │ comptabilisee│
│     ↓        │                   │     ↓        │              │              │         │     ↓        │
│  commandee   │                   │ partiel_livre │              │              │         │   payee      │
└──────────────┘                   │     ↓        │              └──────────────┘         └──────────────┘
  rejetee/annulee                  │    livre      │
                                   │     ↓        │
                                   │    cloture    │
                                   └──────────────┘
```

**Étapes détaillées** :
1. **Demande d'achat** : créée par un chef de chantier ou conducteur de travaux, justifiée, avec lignes (article, quantité, coût estimé). Urgence : normale, urgente, critique.
2. **Approbation** : le responsable achats approuve ou rejette. Transition atomique avec verrou pessimiste.
3. **Bon de commande** : généré depuis la DA approuvée, adressé au fournisseur. Statuts : brouillon → envoyé → confirmé → partiellement livré → livré → clôturé.
4. **Bon de livraison** : réception des marchandises, vérification quantités. Génère un mouvement de stock entrée.
5. **Facture** : réception, validation (compute_totals depuis lignes), comptabilisation. La validation déclenche `CostIntegrationService` qui crée des CostEntry automatiques imputées au projet/lot/BOQ.

## Suivi des coûts et EVM (Earned Value Management)

### Concepts

| Indicateur | Nom | Formule | Signification |
|---|---|---|---|
| BAC | Budget At Completion | Σ budget_baseline | Budget total planifié |
| PV | Planned Value | Budget travail planifié à date | Valeur planifiée |
| EV | Earned Value | % avancement × budget | Valeur acquise |
| AC | Actual Cost | Σ CostEntry | Coût réel dépensé |
| CV | Cost Variance | EV - AC | Écart de coût (positif = sous budget) |
| SV | Schedule Variance | EV - PV | Écart de délai (positif = en avance) |
| CPI | Cost Performance Index | EV / AC | <1 = dépassement, >1 = économie |
| SPI | Schedule Performance Index | EV / PV | <1 = retard, >1 = avance |
| ETC | Estimate To Complete | (BAC - EV) / CPI | Coût restant estimé |
| EAC | Estimate At Completion | AC + ETC | Coût final estimé |
| VAC | Variance At Completion | BAC - EAC | Écart final prévu |
| TCPI | To-Complete Performance Index | (BAC - EV) / (BAC - AC) | Performance requise pour respecter le budget |

### Reporting périodique

Le `PeriodReport` consolide les données sur une période (mois, trimestre) :
- Lignes par lot de travail (WorkPackage) avec budget, engagé, dépensé, ETC, EAC, variance, CPI
- Calculs via `Reporting::EvmCalculator` et `Reporting::VarianceCalculator`
- Workflow : brouillon → soumis → validé → publié → verrouillé
- Verrouillage interdit toute modification ultérieure

### Baselines

- **CostBaseline** : budget initial figé (référence pour écarts)
- **ScheduleBaseline** : planning initial figé (référence pour écarts délai)
- **Rebaseline** : via `Planning::RebaselineService` (contrôlé, tracé)

## Gestion QSSE

### Qualité — Non-conformités

Workflow : `ouverte → analyse → action_corrective → verifiee → cloturee`

- **Détection** : par tout utilisateur sur le chantier (chef de chantier, ouvrier, chargé QSSE)
- **Sévérité** : mineure (cosmétique), majeure (reprise nécessaire), critique (impact structure/sécurité)
- **Coût de reprise** : `rework_cost` tracé, imputé au projet
- **Délai de résolution** : `days_open` calculé depuis `detected_at`

### Sécurité — Incidents

Workflow : `signale → en_analyse → action_en_cours → cloture`

- **Types** : accident avec arrêt, accident sans arrêt, presque-accident, observation, action préventive
- **Sévérité** : faible, modérée, grave, critique
- **Jours perdus** : `days_lost` (arrêt de travail)
- **Arrêt de travail** : `with_work_stoppage?` si `accident_avec_arret`

### Registre des risques

- **Catégories** : technique, financier, planning, sécurité, réglementaire, météo, fournisseur, autre
- **Évaluation** : probabilité (1-5) × impact (1-5) = exposition (1-25)
- **Niveaux** : 1-5 faible, 6-12 modéré, 13-19 élevé, 20-25 critique
- **Stratégies** : éviter, réduire, transférer, accepter
- **Risque résiduel** : évalué après mise en place des mesures de mitigation

## Gestion du stock

### Valorisation

- **CUMP** (Coût Unitaire Moyen Pondéré) : recalculé à chaque entrée
- **FIFO** (First In First Out) : via `StockFifoLayer` — couches de stock avec coût d'achat

### Mouvements

- **Entrée** : réception BC, retour chantier
- **Sortie** : consommation chantier, génère CostEntry auto
- **Transfert** : entre entrepôts
- **Inventaire** : `InventorySession` → `InventoryLine` (écart = différence entre théorique et compté)

### Seuils

- `min_threshold` : déclenche une alerte de réapprovisionnement
- `safety_stock` : niveau critique (priorité haute)
- `ThresholdConfig` : seuils globaux par défaut (fallback si article sans seuil spécifique)

## Comptabilité

### Écritures (JournalEntry)

Double entrée : chaque `JournalEntry` a plusieurs `JournalEntryLine` (compte, débit, crédit). Les écritures sont équilibrées (Σ débit = Σ crédit).

### Périodes comptables

`AccountingPeriod` : exercice annuel ou mensuel. Clôture = verrouillage (aucune écriture possible).

### Exports

- **FEC** (Fichier des Écritures Comptables) : export norme française via `Accounting::FECExportService`
- **Balance** : via `Accounting::BalanceService`
- **Grand livre** : via `Accounting::LedgerService`
- **Lettrage** : via `Accounting::LettrageService` (association facture ↔ paiement)

## Avenants et modifications

### ChangeOrder

- **Types** : avenant client (modification contractuelle), ordre de service (instruction MOA), modification interne, réclamation
- **Impact** : coût (`impact_cost`) et délai (`impact_delay_days`)
- **Workflow** : brouillon → soumis → en_analyse → approuve/rejete → applique
- **Traçabilité** : tout changement de périmètre est documenté et validé

## Propagation de l'avancement

Mécanisme clé de la plateforme : l'avancement remonte automatiquement depuis les tâches vers le projet.

```
Task.progress_pct (saisie utilisateur)
    ↓ after_save callback
WorkPackage.recalculate_progress! (moyenne pondérée par planned_quantity)
    ↓
ProjectPhase.recalculate_progress! (moyenne pondérée par weight)
    ↓
Project.recalculate_progress! (moyenne pondérée par weight des phases)
```

Cette propagation est **silencieuse** (ne bloque jamais une sauvegarde) et utilise `update_column` pour éviter les boucles de callbacks.
