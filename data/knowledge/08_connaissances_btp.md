# EvalTask — Connaissances sectorielles BTP

## Contexte du secteur

Le secteur du BTP (Bâtiment et Travaux Publics) est caractérisé par :
- Des projets de longue durée (mois à années)
- Des budgets importants avec risque de dépassement
- Une forte réglementation (normes de construction, sécurité, environnement)
- Une multiplicité d'intervenants (MOA, MOE, entreprises, sous-traitants, fournisseurs)
- Une gestion documentaire lourde (marchés, avenants, attachements, PV de réception)
- Un suivi financier rigoureux (décomptes, situations de travaux, retenues de garantie)

## Cycle de vie typique d'un projet BTP

### Phase 1 : Conception et préparation
- **Études de faisabilité** : analyse du site, contraintes, budget prévisionnel
- **Avant-projet sommaire (APS)** puis **avant-projet détaillé (APD)**
- **Permis de construire** et autorisations administratives
- **Appel d'offres** : consultation des entreprises, analyse des offres, attribution
- **Marché signé** : contrat avec prix (forfait, unitaires, ou mixte)
- **Ordre de service de démarrage** : démarrage officiel des travaux

### Phase 2 : Exécution des travaux
- **Installation de chantier** : base vie, clôtures, panneaux, raccordements
- **Terrassement** : déblais-remblais, fondations
- **Gros œuvre** : structure, maçonnerie, étanchéité
- **Second œuvre** : cloisons, revêtements, menuiseries, électricité, plomberie, HVAC
- **Finitions** : peinture, sols, équipements
- **VRD extérieurs** : voirie, réseaux, aménagements extérieurs

### Phase 3 : Réception et clôture
- **Réception provisoire** : inspection MOA, levée des réserves
- **Période de garantie** (généralement 1 an)
- **Réception définitive** : levée de toutes les réserves
- **Décompte définitif** : solde de tous les comptes
- **Clôture administrative** : archives, DOE (Dossier d'Ouvrages Exécutés)

## Acteurs du BTP

### Maître d'ouvrage (MOA)
Le client, propriétaire du projet. Il définit le besoin, finance le projet, réceptionne l'ouvrage. Peut être public (collectivité, État) ou privé (promoteur, entreprise).

### Maître d'œuvre (MOE)
Conception et contrôle. Peut être : architecte, bureau d'études, ingénieur-conseil, économiste de la construction. Dans EvalTask : rôle `moe_manager`.

### Entreprise générale
Entreprise principale qui exécute les travaux. Peut sous-traiter certains lots. Dans EvalTask : c'est l'utilisateur principal de la plateforme.

### Sous-traitants
Entreprises spécialisées par corps d'état : plomberie, électricité, peinture, charpente, etc. Dans EvalTask : modélisés via `Supplier` avec `category = sous_traitance`.

### Fournisseurs
Fournisseurs de matériaux (ciment, acier, bois, carrelage...) et d'équipements. Dans EvalTask : `Supplier` avec `category = materiaux` ou `equipement`.

## Documents clés du BTP

| Document | Description | Équivalent EvalTask |
|---|---|---|
| Marché / Contrat | Document contractuel principal | `Project` + `contract_type` |
| BOQ / Bordereau des prix | Liste des ouvrages avec prix unitaires | `BoqItem` |
| Planning (Gantt) | Calendrier d'exécution des travaux | `Task` + `WorkPackage` |
| DA / Demande d'achat | Demande interne d'approvisionnement | `PurchaseRequest` |
| BC / Bon de commande | Commande officielle au fournisseur | `PurchaseOrder` |
| BL / Bon de livraison | Réception des marchandises | `DeliveryNote` |
| Facture | Document comptable de paiement | `Invoice` |
| Attachement de travaux | Relevé des ouvrages exécutés sur site | `ActualEntry` |
| Situation de travaux | Récapitulatif mensuel des ouvrages exécutés | `PeriodReport` |
| PV de réception | Procès-verbal de réception de l'ouvrage | `Project` status → `reception_provisoire` |
| Avenant | Modification contractuelle | `ChangeOrder` |
| Ordre de service (OS) | Instruction du MOA | `ChangeOrder` (type = `ordre_service`) |
| Non-conformité | Écart qualité détecté | `QualityNonconformity` |
| Fiche d'incident | Signalement d'incident sécurité | `SafetyIncident` |
| Registre des risques | Inventaire des risques projet | `RiskRegisterItem` |

## Méthodes de paiement BTP

### Marché à forfait
Prix global forfaitaire. L'entreprise supporte le risque de dépassement. Les situations de travaux sont basées sur le % d'avancement.

### Marché à prix unitaires
Paiement selon les quantités réellement exécutées. Mesuré via attachements de travaux. Le BOQ sert de base au calcul.

### Marché en régie (cost_plus)
Remboursement des coûts réels + marge. Risque pour le MOA. Nécessite une traçabilité rigoureuse des coûts.

### Décompte
Calcul du montant dû à l'entreprise à chaque situation. Inclut :
- Travaux exécutés (quantités × prix unitaires)
- Modifications (avenants, OS)
- Retenue de garantie (5% généralement)
- Avances et acomptes déjà versés
- TVA

## Réglementation QSSE BTP (France/Afrique francophone)

### Sécurité
- **Plan de prévention** : obligatoire pour les travaux dangereux
- **DUERP** : Document Unique d'Évaluation des Risques Professionnels
- **CACES** : Certificat d'Aptitude à la Conduite En Sécurité (engins de chantier)
- **EPI** : Équipements de Protection Individuelle obligatoires (casque, chaussures, gants, harnais)
- **Accident du travail** : déclaration obligatoire, traçabilité via registre

### Qualité
- **DTU** (Documents Techniques Unifiés) : normes d'exécution des travaux
- **Cahier des charges** : spécifications techniques du marché
- **Contrôle qualité** : essais, mesures, inspections à réception
- **Garantie décennale** : 10 ans pour les dommages compromettant la solidité

### Environnement
- **Étude d'impact** : obligatoire pour les projets importants
- **Gestion des déchets** : tri, traçabilité, élimination réglementaire
- **Bruit, poussière, eau** : respect des seuils réglementaires

## Indicateurs de performance BTP

### Coûts
| Indicateur | Formule | Seuil d'alerte |
|---|---|---|
| Écart budgétaire | budget_revised - EAC | > 5% du budget |
| CPI | EV / AC | < 0.9 |
| Coût par m² | budget / surface | vs référence marché |
| Coût par ouvrage | CostEntry / BoqItem | vs prix unitaire planifié |

### Délais
| Indicateur | Formule | Seuil d'alerte |
|---|---|---|
| Écart de délai | EV - PV | < 0 (retard) |
| SPI | EV / PV | < 0.9 |
| Jours de retard | planned_end - today | > 0 sur tâche critique |
| Tâches en retard | count(overdue tasks) | > 10% des tâches actives |

### Qualité
| Indicateur | Formule | Seuil d'alerte |
|---|---|---|
| NC critiques ouvertes | count(severity=critique, status≠cloturee) | > 0 |
| Délai moyen résolution NC | avg(days_open) | > 30 jours |
| Taux de reprise | rework_cost / budget | > 2% |

### Sécurité
| Indicateur | Formule | Seuil d'alerte |
|---|---|---|
| Taux de fréquence | (accidents × 1M) / heures travaillées | > 10 |
| Jours perdus | sum(days_lost) | > 0 |
| Accidents avec arrêt | count(incident_type=accident_avec_arret) | > 0 |
| Presqu'accidents | count(presquaccident) | Tendance à la hausse = vigilance |

## Bonnes pratiques de pilotage

1. **Mettre à jour l'avancement régulièrement** : saisie hebdomadaire minimum sur les tâches actives
2. **Consolider les coûts en temps réel** : ne pas attendre la fin du mois pour saisir les CostEntry
3. **Anticiper les risques** : revue mensuelle du registre des risques, ajuster les stratégies de mitigation
4. **Traquer les écarts dès leur apparition** : un CPI < 1 détecté tôt permet des actions correctives
5. **Documenter les changements** : tout avenant ou OS doit être tracé avec son impact coût + délai
6. **Clôturer les NC rapidement** : plus une NC reste ouverte, plus le coût de reprise augmente
7. **Surveiller le chemin critique** : un retard sur une tâche non critique peut être absorbé, pas sur une tâche critique
