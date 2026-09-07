"""
Notifications proactives — détection d'anomalies dans les données projet.

Analyse les résultats d'outils (get_project_dashboard, get_project_details, etc.)
et détecte les anomalies critiques :
- CPI < 0.9 (dépassement budgétaire)
- SPI < 0.9 (retard)
- Tâches en retard critique
- Incidents QSSE non traités

Les notifications sont injectées dans la réponse de l'assistant.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Seuils d'alerte
CPI_THRESHOLD = 0.9
SPI_THRESHOLD = 0.9
BUDGET_DEVIATION_THRESHOLD_PCT = 10.0


class AnomalyDetector:
    """
    Détecte des anomalies dans les données projet retournées par les outils.

    Retourne une liste de notifications à injecter dans la réponse.
    """

    _instance: AnomalyDetector | None = None

    @classmethod
    def get_instance(cls) -> AnomalyDetector:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        pass

    def analyze_tool_result(self, tool_name: str, result: Any) -> list[dict[str, str]]:
        """
        Analyse le résultat d'un outil et détecte les anomalies.

        Returns:
            Liste de notifications : [{"severity": "warning", "message": "..."}]
        """
        notifications: list[dict[str, str]] = []

        if not result or not isinstance(result, (dict, str)):
            return notifications

        # Si le résultat est une string JSON, essayer de la parser
        if isinstance(result, str):
            try:
                import json

                result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return notifications

        if not isinstance(result, dict):
            return notifications

        # Détection selon le type d'outil
        if tool_name in ("get_project_dashboard", "get_project_details"):
            notifications.extend(self._check_project_metrics(result))

        return notifications

    def _check_project_metrics(self, data: dict) -> list[dict[str, str]]:
        """Détecte les anomalies dans les métriques projet (EVM)."""
        notifications = []

        # CPI (Cost Performance Index)
        cpi = data.get("cpi") or data.get("cost_performance_index")
        if cpi is not None:
            try:
                cpi_val = float(cpi)
                if cpi_val < CPI_THRESHOLD:
                    notifications.append(
                        {
                            "severity": "critical" if cpi_val < 0.8 else "warning",
                            "message": (
                                f"⚠️ **Alerte budget** : CPI = {cpi_val:.2f} "
                                f"(seuil {CPI_THRESHOLD}). Le projet dépasse son budget "
                                f"de {(1 - cpi_val) * 100:.0f}%. "
                                f"Action recommandée : réviser les coûts et identifier les écarts."
                            ),
                        }
                    )
            except (ValueError, TypeError):
                pass

        # SPI (Schedule Performance Index)
        spi = data.get("spi") or data.get("schedule_performance_index")
        if spi is not None:
            try:
                spi_val = float(spi)
                if spi_val < SPI_THRESHOLD:
                    notifications.append(
                        {
                            "severity": "critical" if spi_val < 0.8 else "warning",
                            "message": (
                                f"⚠️ **Alerte planning** : SPI = {spi_val:.2f} "
                                f"(seuil {SPI_THRESHOLD}). Le projet est en retard "
                                f"de {(1 - spi_val) * 100:.0f}%. "
                                f"Action recommandée : identifier les tâches critiques en retard."
                            ),
                        }
                    )
            except (ValueError, TypeError):
                pass

        # Déviation budgétaire en %
        budget_deviation = data.get("budget_deviation_pct") or data.get("budget_variance_pct")
        if budget_deviation is not None:
            try:
                dev_val = float(budget_deviation)
                if abs(dev_val) > BUDGET_DEVIATION_THRESHOLD_PCT:
                    direction = "dépassement" if dev_val > 0 else "économie"
                    notifications.append(
                        {
                            "severity": "warning",
                            "message": (
                                f"📊 **Écart budgétaire** : {dev_val:+.1f}% ({direction}). "
                                f"Au-delà du seuil de ±{BUDGET_DEVIATION_THRESHOLD_PCT}%."
                            ),
                        }
                    )
            except (ValueError, TypeError):
                pass

        # Tâches en retard
        delayed_tasks = data.get("delayed_tasks") or data.get("overdue_tasks")
        if delayed_tasks and isinstance(delayed_tasks, list) and len(delayed_tasks) > 0:
            notifications.append(
                {
                    "severity": "warning",
                    "message": (
                        f"📋 **{len(delayed_tasks)} tâche(s) en retard** détectée(s). "
                        f"Action recommandée : prioriser ces tâches et ajuster le planning."
                    ),
                }
            )

        # Incidents QSSE
        open_incidents = data.get("open_incidents") or data.get("unresolved_incidents")
        if open_incidents and isinstance(open_incidents, (int, float)) and open_incidents > 0:
            notifications.append(
                {
                    "severity": "critical" if open_incidents >= 3 else "warning",
                    "message": (
                        f"🚨 **{open_incidents} incident(s) QSSE non résolu(s)**. "
                        f"Action recommandée : traiter en priorité les incidents critiques."
                    ),
                }
            )

        return notifications

    def format_notifications(self, notifications: list[dict[str, str]]) -> str:
        """Formate les notifications pour injection dans la réponse."""
        if not notifications:
            return ""

        lines = ["", "---", "**🔔 Notifications proactives :**", ""]
        for notif in notifications:
            lines.append(f"- {notif['message']}")
        lines.append("---")

        return "\n".join(lines)
