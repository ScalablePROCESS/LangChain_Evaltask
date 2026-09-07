"""
Endpoints d'ingestion de documents pour le RAG multi-tenant.

Permet à chaque plateforme EvalTask d'envoyer des documents
qui seront vectorisés et stockés dans le namespace du tenant.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from langchain_core.documents import Document
from pydantic import BaseModel

from app.auth.jwt_auth import TenantInfo, check_embed_rate_limit, sanitize_metadata, verify_tenant_token
from app.config import Settings, get_settings
from app.document.adaptive_splitter import AdaptiveMarkdownSplitter
from app.document.extractor import SUPPORTED_EXTENSIONS, extract_text
from app.vectorstore.manager import VectorStoreManager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["embedding"])

# Splitter adaptatif (découpage par section markdown)
_adaptive_splitter = AdaptiveMarkdownSplitter(chunk_size=1000, chunk_overlap=200)


class TextIngestRequest(BaseModel):
    """Requête d'ingestion de texte brut."""

    tenant_id: str
    texts: list[str]
    metadatas: list[dict] | None = None
    openrouter_api_key: str | None = None


class IngestResponse(BaseModel):
    """Réponse après ingestion."""

    status: str
    documents_ingested: int
    chunks_created: int
    tenant_id: str


class SearchRequest(BaseModel):
    """Requête de recherche dans le vectorstore."""

    tenant_id: str
    query: str
    k: int = 5
    include_global: bool = True
    openrouter_api_key: str | None = None


class SearchResult(BaseModel):
    """Résultat de recherche."""

    content: str
    metadata: dict
    source_type: str


class SearchResponse(BaseModel):
    """Réponse de recherche."""

    results: list[SearchResult]
    query: str
    tenant_id: str


@router.post("/api/v1/embed/text", response_model=IngestResponse)
async def ingest_text(
    request: TextIngestRequest,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> IngestResponse:
    """
    Ingère des textes dans le vectorstore du tenant.
    Les textes sont découpés en chunks avant vectorisation.
    """
    if tenant.tenant_id != request.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch.")

    if not request.texts:
        raise HTTPException(status_code=422, detail="Aucun texte fourni.")

    # Rate limiting pour l'embedding
    check_embed_rate_limit(request.tenant_id, settings)

    # Créer des Documents LangChain
    documents = []
    for i, text in enumerate(request.texts):
        metadata = {}
        if request.metadatas and i < len(request.metadatas):
            metadata = sanitize_metadata(request.metadatas[i])
        metadata["tenant_id"] = request.tenant_id
        documents.append(Document(page_content=text, metadata=metadata))

    # Découper en chunks (adaptatif pour préserver les sections)
    chunks = _adaptive_splitter.split_documents(documents)

    # Ingérer dans le vectorstore
    manager = VectorStoreManager.get_instance(settings)
    count = manager.ingest_documents(
        tenant_id=request.tenant_id,
        documents=chunks,
        openrouter_api_key=request.openrouter_api_key,
    )

    logger.info(
        "[%s] Ingéré %d textes → %d chunks",
        request.tenant_id,
        len(request.texts),
        len(chunks),
    )

    return IngestResponse(
        status="ok",
        documents_ingested=len(request.texts),
        chunks_created=count,
        tenant_id=request.tenant_id,
    )


@router.post("/api/v1/embed/file", response_model=IngestResponse)
async def ingest_file(
    tenant_id: str = Form(...),
    file: UploadFile = File(...),
    source_name: str = Form(None),
    openrouter_api_key: str = Form(None),
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> IngestResponse:
    """
    Ingère un fichier (.txt, .md, .csv, .json, .pdf, .docx) dans le vectorstore du tenant.
    """
    if tenant.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch.")

    # Rate limiting pour l'embedding
    check_embed_rate_limit(tenant_id, settings)

    filename = file.filename or "unknown"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Format non supporté. Formats acceptés : {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    # Lecture et extraction du texte
    file_bytes = await file.read()
    try:
        content = extract_text(file_bytes, filename)
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not content.strip():
        raise HTTPException(status_code=422, detail="Aucun texte extractible dans le fichier.")

    doc = Document(
        page_content=content,
        metadata=sanitize_metadata(
            {
                "source": source_name or filename,
                "filename": filename,
                "tenant_id": tenant_id,
            }
        ),
    )

    chunks = _adaptive_splitter.split_documents([doc])

    manager = VectorStoreManager.get_instance(settings)
    count = manager.ingest_documents(
        tenant_id=tenant_id,
        documents=chunks,
        openrouter_api_key=openrouter_api_key,
    )

    logger.info("[%s] Fichier '%s' → %d chunks", tenant_id, filename, len(chunks))

    return IngestResponse(
        status="ok",
        documents_ingested=1,
        chunks_created=count,
        tenant_id=tenant_id,
    )


@router.post("/api/v1/search", response_model=SearchResponse)
async def search_documents(
    request: SearchRequest,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> SearchResponse:
    """Recherche dans le vectorstore du tenant + global."""
    if tenant.tenant_id != request.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch.")

    manager = VectorStoreManager.get_instance(settings)
    docs = manager.search(
        query=request.query,
        tenant_id=request.tenant_id,
        openrouter_api_key=request.openrouter_api_key,
        k=request.k,
        include_global=request.include_global,
    )

    results = [
        SearchResult(
            content=doc.page_content,
            metadata=doc.metadata,
            source_type=doc.metadata.get("source_type", "unknown"),
        )
        for doc in docs
    ]

    return SearchResponse(
        results=results,
        query=request.query,
        tenant_id=request.tenant_id,
    )


# ─── Modèles pour la gestion de documents ───


class DeleteRequest(BaseModel):
    """Requête de suppression de documents par source."""

    tenant_id: str
    source: str
    scope: str = "tenant"


class DeleteResponse(BaseModel):
    """Réponse après suppression."""

    status: str
    deleted_count: int
    source: str
    scope: str


class ListRequest(BaseModel):
    """Requête de listing de documents."""

    tenant_id: str
    scope: str = "tenant"
    source: str | None = None
    limit: int = 100
    offset: int = 0


class DocumentItem(BaseModel):
    """Un document dans la liste."""

    id: str
    metadata: dict


class ListResponse(BaseModel):
    """Réponse de listing."""

    documents: list[DocumentItem]
    count: int
    scope: str
    tenant_id: str | None = None


class CollectionInfoRequest(BaseModel):
    """Requête d'info sur une collection."""

    tenant_id: str | None = None
    scope: str = "tenant"


class CollectionInfoResponse(BaseModel):
    """Infos sur une collection."""

    count: int
    sources: list[str]
    scope: str
    tenant_id: str | None = None


class UpdateRequest(BaseModel):
    """Requête de mise à jour (remplacement) de documents par source."""

    tenant_id: str
    source: str
    scope: str = "tenant"
    texts: list[str]
    metadatas: list[dict] | None = None
    openrouter_api_key: str | None = None


class UpdateResponse(BaseModel):
    """Réponse après mise à jour."""

    status: str
    deleted_count: int
    ingested_count: int
    source: str
    scope: str


# ─── Endpoints de gestion ───


@router.delete("/api/v1/embed/documents", response_model=DeleteResponse)
async def delete_documents(
    request: DeleteRequest,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> DeleteResponse:
    """
    Supprime tous les chunks d'une source donnée.
    Permet de retirer un document obsolète du vectorstore.
    """
    if request.scope == "tenant":
        if tenant.tenant_id != request.tenant_id:
            raise HTTPException(status_code=403, detail="Tenant mismatch.")
    elif request.scope == "global":
        # Seul un admin global peut supprimer la base globale
        if tenant.tenant_id != "admin" and tenant.tenant_id != "default":
            raise HTTPException(status_code=403, detail="Suppression globale réservée à l'admin.")

    manager = VectorStoreManager.get_instance(settings)
    deleted = manager.delete_documents_by_source(
        source=request.source,
        tenant_id=request.tenant_id,
        scope=request.scope,
    )

    logger.info(
        "[%s] Supprimé %d documents (source='%s', scope=%s)", request.tenant_id, deleted, request.source, request.scope
    )

    return DeleteResponse(
        status="ok",
        deleted_count=deleted,
        source=request.source,
        scope=request.scope,
    )


@router.post("/api/v1/embed/list", response_model=ListResponse)
async def list_documents(
    request: ListRequest,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> ListResponse:
    """
    Liste les documents d'une collection avec pagination.
    Filtrable par source.
    """
    if request.scope == "tenant":
        if tenant.tenant_id != request.tenant_id:
            raise HTTPException(status_code=403, detail="Tenant mismatch.")

    manager = VectorStoreManager.get_instance(settings)
    result = manager.list_documents(
        tenant_id=request.tenant_id,
        scope=request.scope,
        source=request.source,
        limit=request.limit,
        offset=request.offset,
    )

    documents = [
        DocumentItem(id=doc_id, metadata=meta or {}) for doc_id, meta in zip(result["ids"], result["metadatas"])
    ]

    return ListResponse(
        documents=documents,
        count=result["count"],
        scope=request.scope,
        tenant_id=request.tenant_id,
    )


@router.post("/api/v1/embed/info", response_model=CollectionInfoResponse)
async def collection_info(
    request: CollectionInfoRequest,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> CollectionInfoResponse:
    """
    Retourne des infos sur une collection : nombre total de documents et liste des sources.
    """
    if request.scope == "tenant":
        if tenant.tenant_id != request.tenant_id:
            raise HTTPException(status_code=403, detail="Tenant mismatch.")

    manager = VectorStoreManager.get_instance(settings)
    info = manager.get_collection_info(
        tenant_id=request.tenant_id,
        scope=request.scope,
    )

    return CollectionInfoResponse(
        count=info["count"],
        sources=info["sources"],
        scope=request.scope,
        tenant_id=request.tenant_id,
    )


@router.put("/api/v1/embed/documents", response_model=UpdateResponse)
async def update_documents(
    request: UpdateRequest,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> UpdateResponse:
    """
    Met à jour les documents d'une source : supprime les anciens chunks, ingère les nouveaux.
    Permet de remplacer un document par sa version à jour.
    """
    if request.scope == "tenant":
        if tenant.tenant_id != request.tenant_id:
            raise HTTPException(status_code=403, detail="Tenant mismatch.")
    elif request.scope == "global":
        if tenant.tenant_id != "admin" and tenant.tenant_id != "default":
            raise HTTPException(status_code=403, detail="Mise à jour globale réservée à l'admin.")

    if not request.texts:
        raise HTTPException(status_code=422, detail="Aucun texte fourni.")

    # Rate limiting pour l'embedding
    check_embed_rate_limit(request.tenant_id, settings)

    # Créer des Documents LangChain
    documents = []
    for i, text in enumerate(request.texts):
        metadata = {"source": request.source}
        if request.metadatas and i < len(request.metadatas):
            metadata.update(sanitize_metadata(request.metadatas[i]))
        if request.scope == "tenant":
            metadata["tenant_id"] = request.tenant_id
        documents.append(Document(page_content=text, metadata=metadata))

    # Découper en chunks
    chunks = _adaptive_splitter.split_documents(documents)

    manager = VectorStoreManager.get_instance(settings)
    result = manager.update_documents_by_source(
        source=request.source,
        new_documents=chunks,
        tenant_id=request.tenant_id,
        scope=request.scope,
        openrouter_api_key=request.openrouter_api_key,
    )

    logger.info(
        "[%s] Mise à jour source='%s' : %d supprimés, %d ingérés",
        request.tenant_id,
        request.source,
        result["deleted_count"],
        result["ingested_count"],
    )

    return UpdateResponse(
        status="ok",
        deleted_count=result["deleted_count"],
        ingested_count=result["ingested_count"],
        source=request.source,
        scope=request.scope,
    )
