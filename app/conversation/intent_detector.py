"""
Détection d'intention légère pour le routage des messages.

Évite les appels LLM inutiles pour les questions simples (salutations,
remerciements, questions fermées) en répondant directement.

Principes :
- LLMOps Engineer : réduction coûts, latence
- LangChain Solution Architect : routage contextuel
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Patterns d'intentions (regex insensible à la casse)
_INTENT_PATTERNS: dict[str, list[re.Pattern]] = {
    "greeting": [
        re.compile(r"^(bonjour|salut|hello|hi|hey|coucou|bonsoir)\b", re.IGNORECASE),
        re.compile(r"^(bonjour|salut|hello)[\s,].*(ça va|comment vas|comment va)", re.IGNORECASE),
    ],
    "thanks": [
        re.compile(r"^(merci|thanks|thank you|parfait|super|génial|nickel)\b", re.IGNORECASE),
        re.compile(r"^(merci).*(beaucoup|pour)", re.IGNORECASE),
    ],
    "bye": [
        re.compile(r"^(au revoir|bye|à bientôt|bonne soirée|bonne journée|ciao)\b", re.IGNORECASE),
    ],
    "help": [
        re.compile(r"^(aide|help|que peux.tu faire|comment ça marche|que fais.tu)\b", re.IGNORECASE),
    ],
}

# Réponses directes par intention (pas d'appel LLM)
_DIRECT_RESPONSES: dict[str, str] = {
    "greeting": (
        "Bonjour ! Je suis l'assistant EvalTask. "
        "Je peux vous aider avec la gestion de projets BTP : "
        "suivi budgétaire, planning, achats, stock, QSSE, et plus encore. "
        "Comment puis-je vous aider aujourd'hui ?"
    ),
    "thanks": "Avec plaisir ! N'hésitez pas si vous avez d'autres questions.",
    "bye": "Au revoir ! Bonne continuation sur EvalTask.",
    "help": (
        "Je suis l'assistant IA d'EvalTask. Voici ce que je peux faire :\n\n"
        "- **Projets** : créer, consulter, analyser un projet\n"
        "- **Budget & coûts** : suivi EVM, écarts, prévisions\n"
        "- **Achats** : commandes, fournisseurs, réception\n"
        "- **Stock** : inventaire, mouvements, alertes\n"
        "- **QSSE** : incidents, non-conformités, registre des risques\n"
        "- **Planning** : tâches, avancement, retards\n\n"
        "Posez-moi votre question ou demandez-moi d'exécuter une action."
    ),
}

# Seuil de longueur pour la détection (messages courts uniquement)
_MAX_SHORT_MESSAGE_LENGTH = 150


class IntentDetector:
    """
    Détecte l'intention d'un message court pour répondre sans appel LLM.

    Évite les coûts et la latence pour les interactions triviales.
    """

    _instance: IntentDetector | None = None

    @classmethod
    def get_instance(cls) -> IntentDetector:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        pass

    def detect(self, message: str) -> str | None:
        """
        Détecte l'intention d'un message.

        Returns:
            Nom de l'intention (greeting, thanks, bye, help) ou None
            si le message nécessite un traitement LLM.
        """
        if not message:
            return None

        # Ne détecter que les messages courts (pas une question complexe)
        stripped = message.strip()
        if len(stripped) > _MAX_SHORT_MESSAGE_LENGTH:
            return None

        for intent, patterns in _INTENT_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(stripped):
                    logger.debug("[intent] Détecté: %s (message: '%s')", intent, stripped[:50])
                    return intent

        return None

    def get_direct_response(self, intent: str) -> str | None:
        """
        Retourne une réponse directe pour une intention donnée.
        Retourne None si aucune réponse directe n'est disponible.
        """
        return _DIRECT_RESPONSES.get(intent)

    def try_direct_response(self, message: str) -> str | None:
        """
        Tente de répondre directement sans LLM.

        Returns:
            La réponse directe si l'intention est détectée, sinon None.
        """
        intent = self.detect(message)
        if not intent:
            return None
        return self.get_direct_response(intent)
