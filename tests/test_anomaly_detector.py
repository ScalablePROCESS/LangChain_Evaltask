"""Tests pour l'AnomalyDetector."""

import json

from app.conversation.anomaly_detector import AnomalyDetector


def test_singleton():
    """AnomalyDetector doit être un singleton."""
    a = AnomalyDetector.get_instance()
    b = AnomalyDetector.get_instance()
    assert a is b


def test_detect_low_cpi():
    """Détecte un CPI bas (dépassement budget)."""
    detector = AnomalyDetector.get_instance()
    result = json.dumps({"cpi": 0.85, "spi": 1.0})
    notifications = detector.analyze_tool_result("get_project_dashboard", result)
    assert len(notifications) >= 1
    assert any("CPI" in n["message"] or "budget" in n["message"].lower() for n in notifications)


def test_detect_low_spi():
    """Détecte un SPI bas (retard planning)."""
    detector = AnomalyDetector.get_instance()
    result = json.dumps({"cpi": 1.0, "spi": 0.82})
    notifications = detector.analyze_tool_result("get_project_dashboard", result)
    assert len(notifications) >= 1
    assert any("SPI" in n["message"] or "retard" in n["message"].lower() for n in notifications)


def test_no_anomaly_when_healthy():
    """Pas de notification quand les indicateurs sont sains."""
    detector = AnomalyDetector.get_instance()
    result = json.dumps({"cpi": 1.05, "spi": 1.1})
    notifications = detector.analyze_tool_result("get_project_dashboard", result)
    assert len(notifications) == 0


def test_detect_delayed_tasks():
    """Détecte des tâches en retard."""
    detector = AnomalyDetector.get_instance()
    result = json.dumps(
        {
            "cpi": 1.0,
            "spi": 1.0,
            "delayed_tasks": [
                {"name": "T1", "status": "delayed"},
                {"name": "T2", "status": "delayed"},
            ],
        }
    )
    notifications = detector.analyze_tool_result("get_project_dashboard", result)
    assert len(notifications) >= 1
    assert any("tâche" in n["message"].lower() for n in notifications)


def test_format_notifications():
    """format_notifications doit retourner une chaîne markdown."""
    detector = AnomalyDetector.get_instance()
    notifications = [
        {"severity": "warning", "message": "Test alert 1"},
        {"severity": "critical", "message": "Test alert 2"},
    ]
    formatted = detector.format_notifications(notifications)
    assert "Notifications" in formatted or "notifications" in formatted.lower()
    assert "Test alert 1" in formatted
    assert "Test alert 2" in formatted


def test_format_empty_notifications():
    """format_notifications avec liste vide doit retourner une chaîne vide."""
    detector = AnomalyDetector.get_instance()
    formatted = detector.format_notifications([])
    assert formatted == ""


def test_unknown_tool_name():
    """Un nom d'outil inconnu ne doit pas générer de notification."""
    detector = AnomalyDetector.get_instance()
    result = json.dumps({"data": "something"})
    notifications = detector.analyze_tool_result("unknown_tool", result)
    assert len(notifications) == 0
