# EvalTask — Outils de l'assistant IA (Tool Calling)

## Architecture

L'assistant IA communique avec la plateforme via un système de **tool calling**. Le serveur LangChain reçoit les questions des utilisateurs, décide quels outils appeler, puis les exécute côté Rails via `AssistantToolExecutor`. Les résultats sont renvoyés au serveur LangChain pour générer la réponse finale.

**Flux** :
1. Rails envoie le message utilisateur + contexte au serveur LangChain
2. Le serveur LangChain (LLM) analyse et demande des tool_calls
3. Rails exécute les outils via `AssistantToolExecutor` (avec vérification Pundit)
4. Rails renvoie les résultats au serveur LangChain
5. Le serveur LangChain génère la réponse finale
6. Maximum 3 rounds de tool calling (`MAX_TOOL_ROUNDS = 3`)

## Outils de consultation (Data Query)

### list_projects
Liste les projets accessibles à l'utilisateur (filtrés par Pundit scope).
- **Filtres** : `status`, `project_type`, `search` (nom/code)
- **Retour** : `count`, `projects[]` (code, name, status, type, city, progress, budget, dates)

### get_project_details
Détails complets d'un projet : budget, avancement, durée, phases, tâches, DA, BC, factures, incidents, NC, risques.
- **Paramètre** : `project_code` (optionnel si projet courant affiché)
- **Retour** : 25+ champs incluant `on_track?`, `elapsed_pct`, `budget_variance`, counts par entité

### get_project_dashboard
Tableau de bord synthétique : KPI financiers, avancement, alertes, coûts, retards.
- **Paramètre** : `project_code` (optionnel)
- **Retour** : `progress_actual`, `elapsed_pct`, `on_track`, `total_costs`, `total_invoiced_ht/ttc`, `total_paid`, `invoices_overdue_count/amount`, `nc_open`, `incidents_open`

### list_purchase_requests
Liste les demandes d'achat avec filtres.
- **Filtres** : `project_code`, `status`, `urgency`
- **Retour** : `count`, `purchase_requests[]` (code, project, status, urgency, justification, requested_by, needed_by, estimated_total)

### list_purchase_orders
Liste les bons de commande.
- **Filtres** : `project_code`, `status`
- **Retour** : `count`, `purchase_orders[]` (code, project, status, supplier, total_ht/ttc, expected_delivery_date)

### list_invoices
Liste les factures avec filtres.
- **Filtres** : `project_code`, `status`, `overdue_only`
- **Retour** : `count`, `invoices[]` (code, project, type, status, supplier, total_ht/ttc, amount_paid, remaining, overdue)

### list_suppliers
Liste les fournisseurs.
- **Filtres** : `category`, `approved_only`
- **Retour** : `count`, `suppliers[]` (code, name, category, approved, active, payment_terms_days, latest_rating)

### list_nonconformities
Liste les non-conformités qualité.
- **Filtres** : `project_code`, `severity`, `status`
- **Retour** : `count`, `nonconformities[]` (code, project, title, severity, status, location, detected_by, assigned_to, days_open, rework_cost)

### list_safety_incidents
Liste les incidents de sécurité.
- **Filtres** : `project_code`, `incident_type`, `severity`, `status`
- **Retour** : `count`, `safety_incidents[]` (code, project, title, type, severity, status, location, occurred_at, reported_by, days_lost)

### list_stock_articles
Liste les articles en stock avec niveaux par entrepôt.
- **Filtres** : `category`, `search`, `low_stock_only`
- **Retour** : `count`, `stock_articles[]` (sku, name, category, unit, valuation_method, total_quantity, min_threshold, low_stock, warehouses[])

### list_tasks
Liste les tâches d'un projet.
- **Filtres** : `project_code`, `status`, `work_package_name`
- **Retour** : `count`, `tasks[]` (name, work_package, status, progress, start_date, end_date, duration)

### get_financial_summary
Résumé financier global ou par projet.
- **Paramètre** : `project_code` (optionnel → global)
- **Retour** : `total_invoices`, `total_ht`, `total_ttc`, `total_paid`, `remaining_to_pay`, `invoices_overdue`, `overdue_amount`, `total_cost_entries`, `total_costs`

## Outils d'action (Action Tools)

### create_purchase_request
Crée une demande d'achat en statut brouillon.
- **Paramètres** : `project_code` (optionnel), `urgency`, `justification` (requis), `needed_by`
- **Retour** : `success`, `message`, `purchase_request` (code, status, urgency, project)

### submit_purchase_request
Soumet une DA pour approbation (brouillon → soumise).
- **Paramètre** : `request_code` (requis)
- **Retour** : `success`, `message`, `purchase_request` (code, status)

### approve_purchase_request
Approuve une DA soumise (soumise → approuvee). Vérifie `PurchaseRequestPolicy#approve?`.
- **Paramètre** : `request_code` (requis)
- **Retour** : `success`, `message`, `purchase_request` (code, status, approved_by)

### report_safety_incident
Signale un nouvel incident de sécurité.
- **Paramètres** : `project_code` (optionnel), `title` (requis), `description`, `incident_type` (requis), `severity` (requis), `location`
- **Retour** : `success`, `message`, `incident` (code, title, severity, status)

### report_nonconformity
Signale une non-conformité qualité.
- **Paramètres** : `project_code` (optionnel), `title` (requis), `description`, `severity` (requis), `location`
- **Retour** : `success`, `message`, `nonconformity` (code, title, severity, status)

### advance_nonconformity
Fait avancer une NC dans son workflow (ouverte → analyse → action_corrective → verifiee → cloturee).
- **Paramètre** : `nc_code` (requis)
- **Retour** : `success`, `message`, `nonconformity` (code, status, previous_status)

### advance_safety_incident
Fait avancer un incident dans son workflow (signale → en_analyse → action_en_cours → cloture).
- **Paramètre** : `incident_code` (requis)
- **Retour** : `success`, `message`, `incident` (code, status, previous_status)

### update_task_progress
Met à jour le pourcentage d'avancement d'une tâche.
- **Paramètres** : `project_code` (optionnel), `task_name` (requis), `progress` 0-100 (requis)
- **Retour** : `success`, `message`, `task` (name, progress, status)

### generate_admin_report
Génère un rapport professionnel. **Ne doit être appelé qu'UNE SEULE FOIS**.
- **Paramètres** :
  - `report_type` (requis) : projects, financial, purchasing, qsse, users, activity
  - `prompt` (requis) : description du contenu attendu
  - `period` : current_month, last_month, current_year, last_30_days, last_90_days, all_time
  - `project_code` : pour un rapport projet ciblé
  - `format` : summary (défaut) ou detailed
  - `export_format` : html (défaut), pdf, word
- **Retour** : `report_type`, `period`, `prompt`, `format`, `export_format`, `data{}`, `download_url` (si pdf/word)
- **Permissions** : admin (tous types), pm_direction (projects, financial, purchasing, qsse, activity), moe_manager (projects, purchasing, qsse, activity), conducteur_travaux (projects, qsse, activity)

## Sécurité et permissions

- **Tous les outils** vérifient les permissions via Pundit (`policy_scope`, `authorize_show!`, `authorize_action!`)
- **L'utilisateur** est identifié par son contexte (rôles, modules accessibles)
- **Le contexte de page** (`page_context`) permet de déterminer le projet courant quand `project_code` n'est pas fourni
- **Aucune donnée** n'est retournée hors du périmètre de l'utilisateur
