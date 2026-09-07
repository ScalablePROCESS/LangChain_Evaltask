"""
Reranking de documents pour améliorer la pertinence du RAG.

Utilise un cross-encoder (sentence-transformers) pour re-scorer les documents
récupérés par la recherche sémantique. Le cross-encoder évalue la pertinence
query-document de manière plus précise que la similarité cosinus.

Modèle par défaut : cross-encoder/ms-marco-MiniLM-L-6-v2 (rapide, ~22MB).

Si sentence-transformers n'est pas disponible ou le modèle ne peut pas être chargé,
le reranking est désactivé silencieusement (fallback = ordre original).
"""

from __future__ import annotations

import logging

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class Reranker:
    """
    Reranker basé sur un cross-encoder HuggingFace.

    Singleton : le modèle n'est chargé qu'une seule fois.
    Fallback gracieux si le modèle n'est pas disponible.
    """

    _instance: Reranker | None = None

    @classmethod
    def get_instance(cls, model_name: str | None = None) -> Reranker:
        if cls._instance is None:
            cls._instance = cls(model_name)
        return cls._instance

    def __init__(self, model_name: str | None = None):
        self._model_name = model_name or DEFAULT_RERANKER_MODEL
        self._cross_encoder = None
        self._loaded = False
        self._load_model()

    def _load_model(self) -> None:
        """Tente de charger le cross-encoder. Fallback silencieux si échec."""
        if self._loaded:
            return

        try:
            from sentence_transformers import CrossEncoder

            logger.info("Chargement cross-encoder : %s", self._model_name)
            self._cross_encoder = CrossEncoder(self._model_name)
            self._loaded = True
            logger.info("Cross-encoder chargé avec succès")
        except ImportError:
            logger.warning(
                "sentence-transformers non installé — reranking désactivé. "
                "Installez avec : pip install sentence-transformers"
            )
            self._loaded = True
        except Exception as exc:
            logger.warning("Chargement cross-encoder échoué : %s — reranking désactivé", exc)
            self._loaded = True

    def rerank(
        self,
        query: str,
        documents: list[Document],
        top_k: int = 5,
    ) -> list[Document]:
        """
        Re-score les documents par pertinence avec le cross-encoder.

        Args:
            query: La requête utilisateur
            documents: Les documents à reranker
            top_k: Nombre de documents à retourner après reranking

        Returns:
            Documents triés par score décroissant, limités à top_k
        """
        if not documents:
            return []

        if self._cross_encoder is None:
            # Fallback : retourner les documents dans l'ordre original
            return documents[:top_k]

        try:
            # Préparer les paires (query, document) pour le cross-encoder
            pairs = [(query, doc.page_content) for doc in documents]

            # Scorer
            scores = self._cross_encoder.predict(pairs)

            # Trier par score décroissant
            scored_docs = list(zip(scores, documents))
            scored_docs.sort(key=lambda x: x[0], reverse=True)

            # Retourner top_k
            reranked = [doc for _, doc in scored_docs[:top_k]]

            logger.debug(
                "[rerank] %d docs → %d (top score: %.4f)",
                len(documents),
                len(reranked),
                scored_docs[0][0] if scored_docs else 0.0,
            )

            return reranked

        except Exception as exc:
            logger.warning("[rerank] Échec reranking : %s — fallback ordre original", exc)
            return documents[:top_k]

    @property
    def is_available(self) -> bool:
        """Retourne True si le cross-encoder est chargé et disponible."""
        return self._cross_encoder is not None
