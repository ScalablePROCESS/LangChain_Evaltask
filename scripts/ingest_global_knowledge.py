"""
Script d'ingestion des connaissances globales BTP dans le vectorstore.

Usage :
    python scripts/ingest_global_knowledge.py

Ce script charge tous les fichiers .md du répertoire data/knowledge/
et les ingère dans la collection globale du vectorstore ChromaDB.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ajouter la racine du projet au path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import get_settings
from app.vectorstore.manager import VectorStoreManager


def main():
    settings = get_settings()
    knowledge_dir = project_root / "data" / "knowledge"

    if not knowledge_dir.exists():
        print(f"❌ Répertoire {knowledge_dir} introuvable.")
        sys.exit(1)

    # Charger tous les fichiers markdown
    documents: list[Document] = []
    for md_file in sorted(knowledge_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        if content.strip():
            documents.append(Document(
                page_content=content,
                metadata={
                    "source": md_file.name,
                    "source_type": "global",
                    "category": "btp_knowledge",
                },
            ))
            print(f"  📄 {md_file.name} ({len(content)} caractères)")

    if not documents:
        print("⚠️  Aucun document trouvé dans data/knowledge/")
        sys.exit(0)

    # Découper en chunks
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    print(f"\n📦 {len(documents)} documents → {len(chunks)} chunks")

    # Ingérer dans le vectorstore global
    manager = VectorStoreManager.get_instance(settings)
    count = manager.ingest_global_documents(chunks)
    from app.vectorstore.manager import GLOBAL_COLLECTION
    print(f"✅ {count} chunks ingérés dans la collection globale '{GLOBAL_COLLECTION}'")


if __name__ == "__main__":
    main()
