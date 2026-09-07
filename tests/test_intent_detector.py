"""Tests pour l'IntentDetector."""

from app.conversation.intent_detector import IntentDetector


def test_singleton():
    """IntentDetector doit être un singleton."""
    a = IntentDetector.get_instance()
    b = IntentDetector.get_instance()
    assert a is b


def test_detect_greeting_french():
    """Détecte 'bonjour' comme greeting."""
    detector = IntentDetector.get_instance()
    assert detector.detect("Bonjour") == "greeting"
    assert detector.detect("Salut, comment ça va ?") == "greeting"


def test_detect_greeting_english():
    """Détecte 'hello' comme greeting."""
    detector = IntentDetector.get_instance()
    assert detector.detect("Hello") == "greeting"
    assert detector.detect("Hi there") == "greeting"


def test_detect_thanks():
    """Détecte les remerciements."""
    detector = IntentDetector.get_instance()
    assert detector.detect("Merci beaucoup") == "thanks"
    assert detector.detect("Thank you") == "thanks"
    assert detector.detect("Parfait, merci") == "thanks"


def test_detect_bye():
    """Détecte les au revoir."""
    detector = IntentDetector.get_instance()
    assert detector.detect("Au revoir") == "bye"
    assert detector.detect("Bye") == "bye"
    assert detector.detect("À bientôt") == "bye"


def test_detect_help():
    """Détecte les demandes d'aide."""
    detector = IntentDetector.get_instance()
    assert detector.detect("Aide") == "help"
    assert detector.detect("Help") == "help"
    assert detector.detect("Que peux-tu faire ?") == "help"


def test_detect_none_for_complex_message():
    """Un message complexe ne doit pas être détecté comme intention simple."""
    detector = IntentDetector.get_instance()
    assert detector.detect("Quel est le budget du projet PRJ-001 ?") is None
    assert detector.detect("Crée une nouvelle demande d'achat pour 500 FCFA") is None


def test_detect_none_for_long_message():
    """Un message trop long ne doit pas être détecté."""
    detector = IntentDetector.get_instance()
    long_msg = "Bonjour " + "bla " * 100
    assert detector.detect(long_msg) is None


def test_detect_none_for_empty():
    """Un message vide doit retourner None."""
    detector = IntentDetector.get_instance()
    assert detector.detect("") is None
    assert detector.detect(None) is None


def test_try_direct_response_greeting():
    """try_direct_response doit retourner une réponse pour greeting."""
    detector = IntentDetector.get_instance()
    response = detector.try_direct_response("Bonjour")
    assert response is not None
    assert "EvalTask" in response or "assistant" in response.lower()


def test_try_direct_response_none():
    """try_direct_response doit retourner None pour un message complexe."""
    detector = IntentDetector.get_instance()
    assert detector.try_direct_response("Analyse le budget du projet") is None


def test_get_direct_response_known():
    """get_direct_response doit retourner une réponse pour une intention connue."""
    detector = IntentDetector.get_instance()
    assert detector.get_direct_response("greeting") is not None
    assert detector.get_direct_response("thanks") is not None
    assert detector.get_direct_response("bye") is not None
    assert detector.get_direct_response("help") is not None


def test_get_direct_response_unknown():
    """get_direct_response doit retourner None pour une intention inconnue."""
    detector = IntentDetector.get_instance()
    assert detector.get_direct_response("unknown") is None
