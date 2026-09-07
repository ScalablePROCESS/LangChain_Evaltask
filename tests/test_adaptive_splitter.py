"""Tests pour le AdaptiveMarkdownSplitter."""

from langchain_core.documents import Document

from app.document.adaptive_splitter import AdaptiveMarkdownSplitter


def test_split_with_markdown_headings():
    """Le splitter doit découper par section markdown."""
    splitter = AdaptiveMarkdownSplitter(chunk_size=1000, chunk_overlap=200)
    content = """# Introduction

Ceci est l'introduction du document.

## Section 1

Contenu de la section 1 avec assez de texte pour être pertinent.

## Section 2

Contenu de la section 2 avec différentes informations.
"""
    doc = Document(page_content=content, metadata={"source": "test.md"})
    chunks = splitter.split_documents([doc])

    assert len(chunks) >= 2
    # Chaque chunk doit avoir un section_title
    for chunk in chunks:
        assert "section_title" in chunk.metadata
    # Les titres doivent être présents
    titles = [c.metadata["section_title"] for c in chunks]
    assert "Introduction" in titles or any("Introduction" in t for t in titles)
    assert "Section 1" in titles or any("Section 1" in t for t in titles)


def test_split_without_headings_falls_back():
    """Sans titres markdown, le splitter fallback doit découper par taille."""
    splitter = AdaptiveMarkdownSplitter(chunk_size=100, chunk_overlap=20)
    content = "Ceci est un texte sans aucun titre markdown. " * 20
    doc = Document(page_content=content, metadata={"source": "test.txt"})
    chunks = splitter.split_documents([doc])

    assert len(chunks) > 1
    # Tous les chunks doivent avoir la métadonnée source
    for chunk in chunks:
        assert chunk.metadata["source"] == "test.txt"


def test_split_empty_document():
    """Un document vide doit retourner une liste vide ou un chunk vide."""
    splitter = AdaptiveMarkdownSplitter()
    doc = Document(page_content="", metadata={"source": "empty.md"})
    chunks = splitter.split_documents([doc])
    # Le splitter ne doit pas crasher
    assert isinstance(chunks, list)


def test_split_preserves_metadata():
    """Les métadonnées du document source doivent être propagées."""
    splitter = AdaptiveMarkdownSplitter()
    content = "# Title\n\nContent here."
    doc = Document(page_content=content, metadata={"source": "doc.pdf", "tenant_id": "t1"})
    chunks = splitter.split_documents([doc])
    assert len(chunks) >= 1
    for chunk in chunks:
        assert chunk.metadata["source"] == "doc.pdf"
        assert chunk.metadata["tenant_id"] == "t1"


def test_split_long_section_subdivides():
    """Une section trop longue (> MAX_SECTION_SIZE) doit être sous-découpée."""
    splitter = AdaptiveMarkdownSplitter(chunk_size=500, chunk_overlap=100)
    # Section > 3000 chars (MAX_SECTION_SIZE) pour forcer le sous-découpage
    long_section = "# Big Section\n\n" + "This is a paragraph with enough text. " * 200
    doc = Document(page_content=long_section, metadata={"source": "big.md"})
    chunks = splitter.split_documents([doc])
    assert len(chunks) > 1
    # Tous les chunks doivent avoir le même section_title
    for chunk in chunks:
        assert chunk.metadata["section_title"] == "Big Section"
