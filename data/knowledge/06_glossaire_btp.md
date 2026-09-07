# EvalTask — Glossaire métier BTP

## A

**Avenant**
Modification contractuelle du marché, signée par le maître d'ouvrage et l'entreprise. Peut modifier le coût, le délai ou le périmètre. Dans EvalTask : `ChangeOrder` avec `change_type = avenant_client`.

**Approbation**
Validation d'une demande d'achat par le responsable achats. Transition `soumise → approuvee` dans le workflow `PurchaseRequest`.

## B

**Baseline**
Référence figée servant de point de comparaison. Dans EvalTask : `CostBaseline` (budget initial) et `ScheduleBaseline` (planning initial). Toute dérive est mesurée par rapport à la baseline.

**BOQ (Bordereau des Prix Unitaires)**
Document contractuel listant les ouvrages élémentaires avec leurs quantités et prix unitaires. Sert de base au suivi financier. Dans EvalTask : modèle `BoqItem` avec quantités planifiées/réalisées, prix, rendements.

**BAC (Budget At Completion)**
Budget total planifié pour achever le projet. Correspond au `budget_baseline` du projet.

## C

**Chemin critique**
Suite de tâches dont la durée totale détermine la durée du projet. Tout retard sur une tâche critique retarde le projet entier. Dans EvalTask : `Task#is_critical_path`.

**CUMP (Coût Unitaire Moyen Pondéré)**
Méthode de valorisation des stocks. Le coût unitaire est recalculé à chaque entrée : CUMP = (valeur stock actuel + valeur entrée) / (quantité stock + quantité entrée).

**CPI (Cost Performance Index)**
Indicateur EVM : EV / AC. Si < 1, le projet dépasse le budget. Si > 1, le projet est sous budget.

**CV (Cost Variance)**
Écart de coût : EV - AC. Positif = sous budget, négatif = dépassement.

## D

**DA (Demande d'Achat)**
Document interne initié par un chef de chantier ou conducteur de travaux pour demander l'achat de matériaux ou services. Dans EvalTask : `PurchaseRequest`.

## E

**EAC (Estimate At Completion)**
Coût total estimé à l'achèvement : AC + ETC. Indique le coût final prévu du projet.

**EVM (Earned Value Management)**
Méthode de pilotage de projet mesurant simultanément les écarts de coût et de délai. Combine la valeur planifiée (PV), la valeur acquise (EV) et le coût réel (AC).

**ETC (Estimate To Complete)**
Coût restant estimé pour achever le projet : (BAC - EV) / CPI.

**EV (Earned Value / Valeur acquise)**
Valeur du travail réellement accompli : % avancement × budget planifié.

## F

**FEC (Fichier des Écritures Comptables)**
Format normalisé d'export des écritures comptables obligatoire en France. Dans EvalTask : `Accounting::FECExportService`.

**FIFO (First In First Out)**
Méthode de valorisation des stocks. Les articles sortent dans l'ordre d'entrée. Dans EvalTask : `StockFifoLayer` trace les couches d'entrée avec leur coût.

## G

**Gros œuvre**
Phase de construction comprenant les fondations, la structure (murs porteurs, poteaux, poutres, planchers), la maçonnerie. Dans EvalTask : `ProjectPhase` avec statut `en_cours` pendant cette étape.

## L

**Lot de travaux**
Subdivision d'un projet correspondant à un corps d'état (gros œuvre, charpente, couverture, électricité, plomberie, etc.). Dans EvalTask : `WorkPackage` avec `level = lot`.

## M

**Maître d'ouvrage (MOA)**
Entité pour laquelle l'ouvrage est construit (le client). Dans EvalTask : `Organization` liée au projet via `project_organizations`.

**Maître d'œuvre (MOE)**
Entité chargée de la conception et du contrôle de l'exécution (bureau d'études, architecte). Dans EvalTask : rôle `moe_manager`.

## N

**NC (Non-conformité)**
Écart par rapport aux spécifications techniques, aux normes ou au cahier des charges. Dans EvalTask : `QualityNonconformity` avec workflow `ouverte → analyse → action_corrective → verifiee → cloturee`.

## O

**Ordre de service (OS)**
Instruction du maître d'ouvrage modifiant l'exécution du marché sans changer le contrat. Dans EvalTask : `ChangeOrder` avec `change_type = ordre_de_service`.

## P

**PV (Planned Value / Valeur planifiée)**
Budget du travail qui aurait dû être accompli à une date donnée.

**Presqu'accident**
Événement qui aurait pu causer un accident mais qui n'a pas entraîné de blessure. Dans EvalTask : `SafetyIncident` avec `incident_type = presquaccident`.

## R

**Réception provisoire**
Acceptation de l'ouvrage par le maître d'ouvrage à la fin des travaux, avec réserves éventuelles. Dans EvalTask : `Project` avec `project_status = reception_provisoire`.

**Réception définitive**
Acceptation sans réserve après levée des réserves et période de garantie. Dans EvalTask : `Project` avec `project_status = reception_definitive`.

**Rendement**
Quantité d'ouvrage réalisée par unité de temps (ex: m³/h, m²/jour). Dans EvalTask : `BoqItem` avec `yield_planned` et `yield_actual`.

## S

**Second œuvre**
Phase de construction postérieure au gros œuvre : cloisons, revêtements, menuiserie, électricité, plomberie, HVAC.

**SPI (Schedule Performance Index)**
Indicateur EVM : EV / PV. Si < 1, le projet est en retard. Si > 1, le projet est en avance.

**SV (Schedule Variance)**
Écart de délai : EV - PV. Positif = en avance, négatif = en retard.

## T

**TCPI (To-Complete Performance Index)**
Performance requise pour respecter le budget initial : (BAC - EV) / (BAC - AC). Si > 1, il faut améliorer la performance.

## V

**VAC (Variance At Completion)**
Écart final prévu : BAC - EAC. Positif = sous budget final, négatif = dépassement final.

**VRD (Voiries et Réseaux Divers)**
Infrastructure d'aménagement : voirie, assainissement, eau potable, électricité, télécommunications, éclairage public. Dans EvalTask : `project_type = vrd`.

## Types de projets (EvalTask)

| Code | Description |
|---|---|
| batiment_residentiel | Bâtiment d'habitation (logements, immeubles) |
| batiment_commercial | Bâtiment commercial (bureaux, commerces, centres commerciaux) |
| batiment_industriel | Bâtiment industriel (usines, entrepôts, ateliers) |
| infrastructure_routiere | Routes, autoroutes, ponts, tunnels |
| ouvrage_art | Ouvrage d'art (ponts, viaducs, tunnels) |
| hydraulique | Ouvrages hydrauliques (barrages, canaux, stations de pompage) |
| vrd | Voiries et réseaux divers |
| equipement_public | Équipements publics (écoles, hôpitaux, stades) |
| amenagement_urbain | Aménagement urbain (places, parcs, espaces publics) |
| energie_renouvelable | Énergie renouvelable (solaire, éolien, biomasse) |

## Types de contrat (EvalTask)

| Code | Description | Risque |
|---|---|---|
| forfait | Prix forfaitaire global | Risque sur l'entreprise (dépassements à sa charge) |
| unit_price | Prix unitaires | Risque partagé (paiement selon quantités réelles) |
| cost_plus | Coût réel + marge | Risque sur le MOA (coût ouvert) |
| mixte | Combinaison de plusieurs modes | Selon lots |
