"""
Définitions des outils EvalTask pour LangChain.

Ces outils ne sont PAS exécutés ici. Ils sont renvoyés comme tool_calls
au serveur Rails EvalTask qui les exécute localement (sécurité des données).
Le résultat est ensuite renvoyé ici pour que le LLM formule sa réponse.
"""

from __future__ import annotations

EVALTASK_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_projects",
            "description": "Liste les projets accessibles à l'utilisateur. Peut filtrer par statut, type ou mot-clé.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filtrer par statut (preparation, execution, completed, cancelled, etc.)",
                    },
                    "project_type": {"type": "string", "description": "Filtrer par type de projet"},
                    "search": {"type": "string", "description": "Recherche par nom ou code"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_details",
            "description": "Récupère les détails complets d'un projet par son code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_code": {"type": "string", "description": "Code du projet (ex: PRJ-2026-001)"},
                },
                "required": ["project_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_dashboard",
            "description": "Récupère le tableau de bord synthétique d'un projet (avancement, budget, KPIs).",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_code": {"type": "string", "description": "Code du projet"},
                },
                "required": ["project_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "Liste les tâches d'un projet ou les tâches assignées à l'utilisateur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_code": {"type": "string", "description": "Filtrer par projet"},
                    "status": {"type": "string", "description": "Filtrer par statut (pending, in_progress, completed)"},
                    "assigned_to_me": {"type": "boolean", "description": "Ne voir que mes tâches"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cost_summary",
            "description": "Récupère le résumé des coûts d'un projet (budget, réalisé, écarts).",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_code": {"type": "string", "description": "Code du projet"},
                },
                "required": ["project_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_purchase_orders",
            "description": "Liste les bons de commande avec filtres optionnels.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_code": {"type": "string", "description": "Filtrer par projet"},
                    "status": {"type": "string", "description": "Filtrer par statut"},
                    "supplier": {"type": "string", "description": "Filtrer par fournisseur"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_incidents",
            "description": "Liste les incidents QSSE (sécurité, non-conformités).",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_code": {"type": "string", "description": "Filtrer par projet"},
                    "severity": {"type": "string", "description": "Filtrer par gravité (low, medium, high, critical)"},
                    "status": {"type": "string", "description": "Filtrer par statut"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_levels",
            "description": "Récupère les niveaux de stock actuels avec alertes de seuil.",
            "parameters": {
                "type": "object",
                "properties": {
                    "warehouse": {"type": "string", "description": "Filtrer par entrepôt"},
                    "search": {"type": "string", "description": "Recherche par nom d'article"},
                    "below_threshold": {"type": "boolean", "description": "Ne montrer que les articles sous le seuil"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_financial_summary",
            "description": "Récupère le résumé financier (factures, trésorerie, écritures).",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "description": "Période (current_month, current_year, custom)"},
                    "project_code": {"type": "string", "description": "Filtrer par projet"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_admin_report",
            "description": "Génère un rapport administratif complet exportable en PDF ou Word.",
            "parameters": {
                "type": "object",
                "properties": {
                    "report_type": {
                        "type": "string",
                        "description": "Type de rapport (projects, financial, purchasing, qsse, users, activity, project)",
                    },
                    "format": {"type": "string", "description": "Niveau de détail (summary, detailed)"},
                    "export_format": {"type": "string", "description": "Format d'export (pdf, word, html)"},
                    "project_code": {
                        "type": "string",
                        "description": "Code du projet (pour rapport de type 'project')",
                    },
                    "period": {
                        "type": "string",
                        "description": "Période (current_month, current_quarter, current_year)",
                    },
                    "prompt": {"type": "string", "description": "Consigne spécifique pour le rapport"},
                },
                "required": ["report_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_data",
            "description": "Recherche transversale dans les données EvalTask (projets, tâches, fournisseurs, articles, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Terme de recherche"},
                    "scope": {
                        "type": "string",
                        "description": "Limiter la recherche (projects, tasks, suppliers, articles, invoices)",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


def get_tool_definitions() -> list[dict]:
    """Retourne les définitions d'outils au format OpenAI/OpenRouter."""
    return EVALTASK_TOOLS
