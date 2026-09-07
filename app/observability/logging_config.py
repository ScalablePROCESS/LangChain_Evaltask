"""
Configuration du logging structuré JSON.

Quand log_format=json, les logs sont émis au format JSON pour intégration
ELK/Datadog/Loki. Sinon, format texte lisible (défaut).

Usage :
    from app.observability.logging_config import setup_logging
    setup_logging(settings)
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

from app.config import Settings


class JsonFormatter(logging.Formatter):
    """
    Formateur JSON pour logs structurés.

    Champs : timestamp, level, logger, message, + tous les extra fields.
    """

    _SENSITIVE_KEYS = {"api_key", "openrouter_api_key", "jwt_secret", "embedding_api_key", "password", "token"}

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Ajouter les champs extra (attributs non standards)
        standard_attrs = {
            "name",
            "msg",
            "args",
            "created",
            "relativeCreated",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "filename",
            "module",
            "pathname",
            "thread",
            "threadName",
            "process",
            "processName",
            "levelname",
            "levelno",
            "message",
            "msecs",
        }
        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                # Masquer les champs sensibles
                if any(s in key.lower() for s in self._SENSITIVE_KEYS):
                    log_entry[key] = "***REDACTED***"
                else:
                    log_entry[key] = value

        # Ajouter l'exception si présente
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """
    Formateur texte lisible avec couleurs optionnelles.
    """

    def format(self, record: logging.LogRecord) -> str:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
        msg = record.getMessage()

        # Inclure les extra fields entre crochets
        standard_attrs = {
            "name",
            "msg",
            "args",
            "created",
            "relativeCreated",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "filename",
            "module",
            "pathname",
            "thread",
            "threadName",
            "process",
            "processName",
            "levelname",
            "levelno",
            "message",
            "msecs",
        }
        extras = []
        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                extras.append(f"{key}={value}")

        extra_str = f" [{', '.join(extras)}]" if extras else ""
        exc_str = ""
        if record.exc_info and record.exc_info[1]:
            exc_str = "\n" + self.formatException(record.exc_info)

        return f"{timestamp} [{record.levelname}] {record.name}: {msg}{extra_str}{exc_str}"


def setup_logging(settings: Settings) -> None:
    """
    Configure le logging selon le format défini dans les settings.

    log_format = "json" → JSON structuré pour ELK/Datadog
    log_format = "text" → texte lisible (défaut)
    """
    log_format = getattr(settings, "log_format", "text")
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Choisir le formateur
    if log_format == "json":
        formatter: logging.Formatter = JsonFormatter()
    else:
        formatter = TextFormatter()

    # Configurer le handler root
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Appliquer sur le logger root
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Réduire le bruit des libraires tierces
    for noisy in ("httpx", "httpcore", "chromadb", "urllib3", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
