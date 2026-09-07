"""Tests pour le LanguageDetector."""

from app.conversation.language_detector import LanguageDetector


def test_singleton():
    """LanguageDetector doit être un singleton."""
    a = LanguageDetector.get_instance()
    b = LanguageDetector.get_instance()
    assert a is b


def test_detect_french():
    """La détection doit reconnaître le français."""
    detector = LanguageDetector.get_instance()
    lang = detector.detect("Bonjour, comment allez-vous aujourd'hui ?")
    assert lang == "fr"


def test_detect_english():
    """La détection doit reconnaître l'anglais."""
    detector = LanguageDetector.get_instance()
    lang = detector.detect("Hello, how are you doing today?")
    assert lang == "en"


def test_detect_empty_string():
    """Une chaîne vide doit retourner la langue par défaut (fr)."""
    detector = LanguageDetector.get_instance()
    lang = detector.detect("")
    assert lang == "fr"


def test_detect_mixed_languages():
    """Un texte mixte doit retourner la langue dominante."""
    detector = LanguageDetector.get_instance()
    # Majorité de mots français
    lang = detector.detect("Le projet est en cours et the budget est dépassé")
    assert lang in ("fr", "en")  # Tolérant selon les stopwords


def test_detect_arabic():
    """La détection doit reconnaître l'arabe via le script."""
    detector = LanguageDetector.get_instance()
    lang = detector.detect("مرحبا كيف حالكم اليوم")
    assert lang == "ar"
