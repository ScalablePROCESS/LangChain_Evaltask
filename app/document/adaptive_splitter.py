"""
Découpage adaptatif de documents par section markdown.

Au lieu d'un découpage fixe (1000 chars), ce splitter détecte les sections
markdown (titres #, ##, ###) et découpe par section. Les sections trop longues
sont sous-découpées avec un RecursiveCharacterTextSplitter.

Avantages :
- Préserve la cohérence sémantique des sections
- Évite de couper au milieu d'un paragraphe important
- Les métadonnées de section (titre) sont propagées dans chaque chunk
"""

from __future__ import annotations

import logging
import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

# Pattern pour détecter les titres markdown
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# Tailles par défaut
DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 200
MAX_SECTION_SIZE = 3000  # Si une section dépasse, sous-découpage


class AdaptiveMarkdownSplitter:
    """
    Splitter adaptatif qui découpe par section markdown.

    Utilisation :
        splitter = AdaptiveMarkdownSplitter()
        chunks = splitter.split_documents([doc])
    """

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ):
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._fallback_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def split_documents(self, documents: list[Document]) -> list[Document]:
        """
        Découpe une liste de documents par section markdown.

        Chaque chunk hérite des métadonnées du document source + un champ
        `section_title` avec le titre de la section.
        """
        all_chunks: list[Document] = []

        for doc in documents:
            chunks = self._split_single(doc)
            all_chunks.extend(chunks)

        return all_chunks

    def _split_single(self, doc: Document) -> list[Document]:
        """Découpe un seul document par section markdown."""
        content = doc.page_content
        base_metadata = dict(doc.metadata)

        # Détecter les positions des titres
        headings = list(_HEADING_PATTERN.finditer(content))

        # Pas de titres markdown → fallback RecursiveCharacterTextSplitter
        if not headings:
            return self._fallback_splitter.split_documents([doc])

        # Découper par section
        sections: list[tuple[str, str]] = []  # (title, content)
        for i, match in enumerate(headings):
            title = match.group(2).strip()
            start = match.start()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(content)
            section_content = content[start:end].strip()
            if section_content:
                sections.append((title, section_content))

        # Texte avant le premier titre (si présent)
        if headings[0].start() > 0:
            pre_content = content[: headings[0].start()].strip()
            if pre_content:
                sections.insert(0, ("Introduction", pre_content))

        if not sections:
            return self._fallback_splitter.split_documents([doc])

        # Traiter chaque section
        chunks: list[Document] = []
        for title, section_content in sections:
            if len(section_content) <= MAX_SECTION_SIZE:
                # Section assez courte → un seul chunk
                chunks.append(
                    Document(
                        page_content=section_content,
                        metadata={**base_metadata, "section_title": title},
                    )
                )
            else:
                # Section trop longue → sous-découpage
                sub_doc = Document(page_content=section_content, metadata=base_metadata)
                sub_chunks = self._fallback_splitter.split_documents([sub_doc])
                for j, sub in enumerate(sub_chunks):
                    chunks.append(
                        Document(
                            page_content=sub.page_content,
                            metadata={
                                **base_metadata,
                                "section_title": title,
                                "chunk_index": j,
                            },
                        )
                    )

        logger.debug(
            "[adaptive_split] %d sections → %d chunks (doc source: %s)",
            len(sections),
            len(chunks),
            base_metadata.get("source", "unknown"),
        )

        return chunks
