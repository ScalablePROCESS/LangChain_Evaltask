"""
Gestionnaire de vectorstore multi-tenant pour le RAG EvalTask.

Utilise ChromaDB avec des collections isolées par tenant_id.
Une collection "global" contient les connaissances partagées (BTP, QSSE, normes).
"""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.config import Settings, get_settings
from app.vectorstore.reranker import Reranker

logger = logging.getLogger(__name__)

# Collection partagée pour les connaissances globales BTP
GLOBAL_COLLECTION = "evaltask_global"


class VectorStoreManager:
    """Gère les vectorstores isolés par tenant avec une couche globale partagée."""

    _instance: VectorStoreManager | None = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, settings: Settings | None = None) -> VectorStoreManager:
        """Retourne l'instance singleton (thread-safe)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(settings)
        return cls._instance

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        persist_dir = self._settings.chroma_persist_dir
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        logger.info("ChromaDB initialisé dans %s", persist_dir)

        self._embeddings: Embeddings | None = None
        self._stores: dict[str, Chroma] = {}
        self._reranker: Reranker | None = None

    LOCAL_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

    def _get_embeddings(self, openrouter_api_key: str | None = None) -> Embeddings:
        """
        Retourne l'instance d'embedding local HuggingFace (singleton, gratuit, sans clé API).
        Le modèle n'est chargé qu'une seule fois.
        """
        if self._embeddings is None:
            try:
                from langchain_huggingface import HuggingFaceEmbeddings
            except ImportError:
                raise ImportError(
                    "langchain-huggingface n'est pas installé. "
                    "Installez-le avec : pip install langchain-huggingface sentence-transformers"
                )
            logger.info("Chargement embeddings locaux HuggingFace : %s", self.LOCAL_EMBEDDING_MODEL)
            self._embeddings = HuggingFaceEmbeddings(model_name=self.LOCAL_EMBEDDING_MODEL)
        return self._embeddings

    def _collection_name(self, tenant_id: str) -> str:
        """Nom de la collection ChromaDB pour un tenant."""
        safe_id = tenant_id.replace("-", "_").replace(" ", "_").lower()
        return f"tenant_{safe_id}"

    def get_tenant_store(self, tenant_id: str, openrouter_api_key: str | None = None) -> Chroma:
        """Retourne le vectorstore isolé d'un tenant (mis en cache)."""
        name = self._collection_name(tenant_id)
        if name not in self._stores:
            self._stores[name] = Chroma(
                client=self._client,
                collection_name=name,
                embedding_function=self._get_embeddings(openrouter_api_key),
            )
        return self._stores[name]

    def get_global_store(self, openrouter_api_key: str | None = None) -> Chroma:
        """Retourne le vectorstore des connaissances globales BTP (mis en cache)."""
        if GLOBAL_COLLECTION not in self._stores:
            self._stores[GLOBAL_COLLECTION] = Chroma(
                client=self._client,
                collection_name=GLOBAL_COLLECTION,
                embedding_function=self._get_embeddings(openrouter_api_key),
            )
        return self._stores[GLOBAL_COLLECTION]

    def ingest_documents(
        self,
        tenant_id: str,
        documents: list[Document],
        openrouter_api_key: str | None = None,
    ) -> int:
        """
        Ingère des documents dans le vectorstore d'un tenant.
        Retourne le nombre de documents ingérés.
        """
        store = self.get_tenant_store(tenant_id, openrouter_api_key)
        store.add_documents(documents)
        logger.info("Ingéré %d documents pour tenant %s", len(documents), tenant_id)
        return len(documents)

    def ingest_global_documents(
        self,
        documents: list[Document],
        openrouter_api_key: str | None = None,
    ) -> int:
        """Ingère des documents dans la base de connaissances globale."""
        store = self.get_global_store(openrouter_api_key)
        store.add_documents(documents)
        logger.info("Ingéré %d documents globaux", len(documents))
        return len(documents)

    def search(
        self,
        query: str,
        tenant_id: str,
        openrouter_api_key: str | None = None,
        k: int = 5,
        include_global: bool = True,
        use_reranking: bool = True,
    ) -> list[Document]:
        """
        Recherche hybride dans le vectorstore du tenant + global.

        1. Recherche sémantique (similarité cosinus via embeddings)
        2. Recherche par mots-clés (filtrage where_document dans ChromaDB)
        3. Fusion des résultats (deduplication)
        4. Reranking par cross-encoder (si disponible)

        Retourne les documents les plus pertinents, triés par score.
        """
        # Over-fetch pour avoir plus de candidats à reranker
        fetch_k = k * 3 if use_reranking else k

        results: list[Document] = []
        seen_contents: set[str] = set()

        # --- 1. Recherche sémantique ---
        semantic_docs = self._semantic_search(query, tenant_id, openrouter_api_key, fetch_k, include_global)
        for doc in semantic_docs:
            content_hash = hash(doc.page_content[:200])
            if content_hash not in seen_contents:
                seen_contents.add(content_hash)
                results.append(doc)

        # --- 2. Recherche par mots-clés ---
        keyword_docs = self._keyword_search(query, tenant_id, openrouter_api_key, fetch_k, include_global)
        for doc in keyword_docs:
            content_hash = hash(doc.page_content[:200])
            if content_hash not in seen_contents:
                seen_contents.add(content_hash)
                results.append(doc)

        # --- 3. Reranking ---
        if use_reranking and len(results) > k:
            results = self._rerank_results(query, results, k)
        else:
            results = results[:k]

        logger.debug(
            "[search] query='%s' → %d docs (semantic=%d, keyword=%d, reranked=%s)",
            query[:50],
            len(results),
            len(semantic_docs),
            len(keyword_docs),
            use_reranking,
        )

        return results

    def _semantic_search(
        self,
        query: str,
        tenant_id: str,
        openrouter_api_key: str | None,
        k: int,
        include_global: bool,
    ) -> list[Document]:
        """Recherche sémantique par similarité d'embeddings."""
        results: list[Document] = []

        tenant_store = self.get_tenant_store(tenant_id, openrouter_api_key)
        try:
            tenant_results = tenant_store.similarity_search(query, k=k)
            for doc in tenant_results:
                doc.metadata["source_type"] = "tenant"
                doc.metadata["search_method"] = "semantic"
            results.extend(tenant_results)
        except Exception as exc:
            logger.warning("Recherche sémantique tenant %s échouée : %s", tenant_id, exc)

        if include_global:
            global_store = self.get_global_store(openrouter_api_key)
            try:
                global_results = global_store.similarity_search(query, k=k)
                for doc in global_results:
                    doc.metadata["source_type"] = "global"
                    doc.metadata["search_method"] = "semantic"
                results.extend(global_results)
            except Exception as exc:
                logger.warning("Recherche sémantique globale échouée : %s", exc)

        return results

    def _keyword_search(
        self,
        query: str,
        tenant_id: str,
        openrouter_api_key: str | None,
        k: int,
        include_global: bool,
    ) -> list[Document]:
        """
        Recherche par mots-clés via where_document de ChromaDB.
        Utilise $or pour une seule requête par collection au lieu de boucler par mot-clé.
        """
        # Extraire les mots-clés significatifs
        words = re.findall(r"\b\w{4,}\b", query.lower())
        if not words:
            return []

        keywords = list(set(words))[:5]  # Limiter à 5 mots-clés

        # Construire la condition $or pour tous les mots-clés en une requête
        where_document = {"$or": [{"$contains": kw} for kw in keywords]}

        results: list[Document] = []

        # Recherche dans la collection du tenant
        try:
            tenant_store = self.get_tenant_store(tenant_id, openrouter_api_key)
            collection = tenant_store._collection
            chroma_results = collection.query(
                query_texts=None,
                where_document=where_document,
                n_results=k,
            )
            if chroma_results and chroma_results.get("documents"):
                for doc_text, metadata in zip(chroma_results["documents"][0], chroma_results["metadatas"][0]):
                    results.append(
                        Document(
                            page_content=doc_text,
                            metadata={**metadata, "source_type": "tenant", "search_method": "keyword"},
                        )
                    )
        except Exception as exc:
            logger.debug("Recherche mots-clés tenant échouée : %s", exc)

        # Recherche dans la collection globale
        if include_global:
            try:
                global_store = self.get_global_store(openrouter_api_key)
                collection = global_store._collection
                chroma_results = collection.query(
                    query_texts=None,
                    where_document=where_document,
                    n_results=k,
                )
                if chroma_results and chroma_results.get("documents"):
                    for doc_text, metadata in zip(chroma_results["documents"][0], chroma_results["metadatas"][0]):
                        results.append(
                            Document(
                                page_content=doc_text,
                                metadata={**metadata, "source_type": "global", "search_method": "keyword"},
                            )
                        )
            except Exception as exc:
                logger.debug("Recherche mots-clés globale échouée : %s", exc)

        return results

    def _rerank_results(
        self,
        query: str,
        documents: list[Document],
        top_k: int,
    ) -> list[Document]:
        """Rerank les documents avec le cross-encoder."""
        if self._reranker is None:
            self._reranker = Reranker.get_instance()

        return self._reranker.rerank(query, documents, top_k=top_k)

    def list_tenant_collections(self) -> list[str]:
        """Liste toutes les collections de tenants existantes."""
        collections = self._client.list_collections()
        return [c.name for c in collections]

    def delete_tenant_data(self, tenant_id: str) -> None:
        """Supprime toutes les données d'un tenant."""
        collection_name = self._collection_name(tenant_id)
        try:
            self._client.delete_collection(collection_name)
            self._stores.pop(collection_name, None)
            logger.info("Collection %s supprimée", collection_name)
        except ValueError:
            logger.warning("Collection %s introuvable", collection_name)

    def delete_documents_by_source(
        self,
        source: str,
        tenant_id: str | None = None,
        scope: str = "tenant",
    ) -> int:
        """
        Supprime tous les chunks dont la métadonnée 'source' correspond.

        Args:
            source: Valeur de la métadonnée 'source' à supprimer
            tenant_id: ID du tenant (requis si scope='tenant')
            scope: 'tenant' ou 'global'

        Returns:
            Nombre de documents supprimés
        """
        if scope == "global":
            collection_name = GLOBAL_COLLECTION
        else:
            if not tenant_id:
                raise ValueError("tenant_id requis pour scope='tenant'")
            collection_name = self._collection_name(tenant_id)

        try:
            collection = self._client.get_collection(collection_name)
        except ValueError:
            logger.warning("Collection %s introuvable pour suppression", collection_name)
            return 0

        # Récupérer les IDs des documents correspondant à la source
        results = collection.get(where={"source": source})
        ids = results.get("ids", [])
        if not ids:
            logger.info("Aucun document avec source='%s' dans %s", source, collection_name)
            return 0

        collection.delete(ids=ids)
        logger.info(
            "Supprimé %d documents (source='%s') de %s",
            len(ids),
            source,
            collection_name,
        )
        return len(ids)

    def list_documents(
        self,
        tenant_id: str | None = None,
        scope: str = "tenant",
        source: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """
        Liste les documents d'une collection avec métadonnées.

        Args:
            tenant_id: ID du tenant (requis si scope='tenant')
            scope: 'tenant' ou 'global'
            source: Filtrer par source (optionnel)
            limit: Nombre max de résultats
            offset: Décalage pour pagination

        Returns:
            Dict avec ids, metadatas, count
        """
        if scope == "global":
            collection_name = GLOBAL_COLLECTION
        else:
            if not tenant_id:
                raise ValueError("tenant_id requis pour scope='tenant'")
            collection_name = self._collection_name(tenant_id)

        try:
            collection = self._client.get_collection(collection_name)
        except ValueError:
            return {"ids": [], "metadatas": [], "count": 0}

        where = {"source": source} if source else None
        results = collection.get(
            where=where,
            limit=limit,
            offset=offset,
            include=["metadatas"],
        )

        return {
            "ids": results.get("ids", []),
            "metadatas": results.get("metadatas", []),
            "count": len(results.get("ids", [])),
        }

    def get_collection_info(
        self,
        tenant_id: str | None = None,
        scope: str = "tenant",
    ) -> dict:
        """
        Retourne des informations sur une collection (nombre de documents, sources).

        Returns:
            Dict avec count, sources (liste unique des sources)
        """
        if scope == "global":
            collection_name = GLOBAL_COLLECTION
        else:
            if not tenant_id:
                raise ValueError("tenant_id requis pour scope='tenant'")
            collection_name = self._collection_name(tenant_id)

        try:
            collection = self._client.get_collection(collection_name)
        except ValueError:
            return {"count": 0, "sources": []}

        results = collection.get(include=["metadatas"])
        metadatas = results.get("metadatas", [])
        sources = list({m.get("source", "unknown") for m in metadatas if m})

        return {
            "count": len(results.get("ids", [])),
            "sources": sorted(sources),
        }

    def update_documents_by_source(
        self,
        source: str,
        new_documents: list[Document],
        tenant_id: str | None = None,
        scope: str = "tenant",
        openrouter_api_key: str | None = None,
    ) -> dict:
        """
        Met à jour les documents d'une source : supprime les anciens, ingère les nouveaux.

        Returns:
            Dict avec deleted_count, ingested_count
        """
        deleted = self.delete_documents_by_source(
            source=source,
            tenant_id=tenant_id,
            scope=scope,
        )

        if not new_documents:
            return {"deleted_count": deleted, "ingested_count": 0}

        # Ajouter la métadonnée source si absente
        for doc in new_documents:
            if "source" not in doc.metadata:
                doc.metadata["source"] = source

        if scope == "global":
            ingested = self.ingest_global_documents(new_documents, openrouter_api_key)
        else:
            if not tenant_id:
                raise ValueError("tenant_id requis pour scope='tenant'")
            ingested = self.ingest_documents(
                tenant_id=tenant_id,
                documents=new_documents,
                openrouter_api_key=openrouter_api_key,
            )

        logger.info(
            "Mise à jour source='%s' : %d supprimés, %d ingérés",
            source,
            deleted,
            ingested,
        )
        return {"deleted_count": deleted, "ingested_count": ingested}
