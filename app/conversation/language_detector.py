"""
Détection de langue automatique pour les messages utilisateurs.

Permet à l'assistant de répondre dans la langue de l'utilisateur.
Détection légère par analyse de stopwords (pas de dépendance externe).

Langues supportées : français, anglais, espagnol, allemand, arabe.
"""

from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

# Stopwords par langue (mots les plus fréquents)
_STOPWORDS: dict[str, set[str]] = {
    "fr": {
        "le",
        "la",
        "les",
        "un",
        "une",
        "des",
        "de",
        "du",
        "et",
        "ou",
        "mais",
        "donc",
        "or",
        "ni",
        "car",
        "que",
        "qui",
        "quoi",
        "dans",
        "pour",
        "par",
        "sur",
        "sous",
        "avec",
        "sans",
        "ce",
        "cette",
        "ces",
        "mon",
        "ma",
        "mes",
        "ton",
        "ta",
        "tes",
        "son",
        "sa",
        "ses",
        "notre",
        "votre",
        "leur",
        "je",
        "tu",
        "il",
        "elle",
        "nous",
        "vous",
        "ils",
        "elles",
        "est",
        "sont",
        "a",
        "ai",
        "as",
        "avons",
        "avez",
        "ont",
        "pas",
        "ne",
        "plus",
        "très",
        "bien",
    },
    "en": {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "so",
        "because",
        "if",
        "when",
        "where",
        "what",
        "who",
        "which",
        "in",
        "on",
        "at",
        "to",
        "for",
        "with",
        "without",
        "this",
        "that",
        "these",
        "those",
        "my",
        "your",
        "his",
        "her",
        "its",
        "our",
        "their",
        "i",
        "you",
        "he",
        "she",
        "it",
        "we",
        "they",
        "is",
        "are",
        "was",
        "were",
        "have",
        "has",
        "had",
        "not",
        "no",
        "very",
    },
    "es": {
        "el",
        "la",
        "los",
        "las",
        "un",
        "una",
        "unos",
        "unas",
        "y",
        "o",
        "pero",
        "porque",
        "si",
        "cuando",
        "donde",
        "que",
        "quien",
        "cual",
        "en",
        "para",
        "por",
        "con",
        "sin",
        "este",
        "esta",
        "estos",
        "estas",
        "mi",
        "tu",
        "su",
        "nuestro",
        "vuestro",
        "yo",
        "tu",
        "el",
        "ella",
        "nosotros",
        "vosotros",
        "ellos",
        "es",
        "son",
        "esta",
        "estan",
        "no",
        "muy",
        "bien",
    },
    "de": {
        "der",
        "die",
        "das",
        "ein",
        "eine",
        "und",
        "oder",
        "aber",
        "weil",
        "wenn",
        "wo",
        "was",
        "wer",
        "in",
        "auf",
        "mit",
        "ohne",
        "dieser",
        "diese",
        "dieses",
        "mein",
        "dein",
        "sein",
        "ihr",
        "unser",
        "euer",
        "ich",
        "du",
        "er",
        "sie",
        "es",
        "wir",
        "ihr",
        "sie",
        "ist",
        "sind",
        "war",
        "waren",
        "haben",
        "hat",
        "hatte",
        "nicht",
        "kein",
        "sehr",
    },
}

# Script arabe : plage Unicode
_ARABIC_PATTERN = re.compile(r"[\u0600-\u06FF\u0750-\u077F]")

# Langue par défaut
DEFAULT_LANGUAGE = "fr"

# Labels pour affichage
LANGUAGE_LABELS: dict[str, str] = {
    "fr": "Français",
    "en": "English",
    "es": "Español",
    "de": "Deutsch",
    "ar": "العربية",
}


class LanguageDetector:
    """
    Détecteur de langue léger basé sur les stopwords.

    Pas de dépendance externe, détection rapide (< 1ms).
    """

    _instance: LanguageDetector | None = None

    @classmethod
    def get_instance(cls) -> LanguageDetector:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        pass

    def detect(self, text: str) -> str:
        """
        Détecte la langue d'un texte.

        Returns:
            Code langue : 'fr', 'en', 'es', 'de', 'ar'
            Défaut : 'fr' si indéterminé
        """
        if not text or not text.strip():
            return DEFAULT_LANGUAGE

        # Détection arabe par script
        if _ARABIC_PATTERN.search(text):
            return "ar"

        # Normalisation : lowercase + suppression accents
        normalized = self._normalize(text)

        # Tokenisation simple
        words = set(normalized.split())
        if not words:
            return DEFAULT_LANGUAGE

        # Score par langue : intersection avec stopwords
        scores: dict[str, int] = {}
        for lang, stopwords in _STOPWORDS.items():
            score = len(words & stopwords)
            if score > 0:
                scores[lang] = score

        if not scores:
            return DEFAULT_LANGUAGE

        # Langue avec le score le plus élevé
        best_lang = max(scores, key=scores.get)
        logger.debug("[lang] Détecté: %s (scores: %s)", best_lang, scores)
        return best_lang

    def _normalize(self, text: str) -> str:
        """Normalise le texte pour la comparaison."""
        # Supprimer les accents
        nfkd = unicodedata.normalize("NFKD", text.lower())
        ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
        # Ponctuation → espaces
        cleaned = re.sub(r"[^\w\s]", " ", ascii_text)
        # Coller les espaces multiples
        return re.sub(r"\s+", " ", cleaned).strip()

    def get_language_label(self, lang_code: str) -> str:
        """Retourne le label humain d'une langue."""
        return LANGUAGE_LABELS.get(lang_code, lang_code)
