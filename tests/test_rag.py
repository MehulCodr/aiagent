from __future__ import annotations

from pathlib import Path

from code_agent.rag import RepositoryRAG


def test_rag_indexes_chunks_retrieves_and_ignores_cache_dirs(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(
        "def reconcile_payment():\n    return 'invoice ledger match'\n",
        encoding="utf-8",
    )
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignored.js").write_text("reconcile_payment", encoding="utf-8")
    (tmp_path / ".agent" / "sessions").mkdir(parents=True)
    (tmp_path / ".agent" / "sessions" / "ignored.json").write_text("invoice", encoding="utf-8")

    rag = RepositoryRAG(tmp_path, chunk_lines=1, overlap=0)
    index = rag.index()

    assert [chunk.path for chunk in index.chunks] == ["src/app.py", "src/app.py"]
    assert rag.cache_path.exists()

    retrieved = rag.retrieve("invoice ledger reconcile payment", limit=1)
    assert retrieved
    assert retrieved[0].chunk.path == "src/app.py"
    assert retrieved[0].chunk.start_line in {1, 2}
    assert "src/app.py:" in retrieved[0].chunk.citation

    cached = rag.index()
    assert cached.files == index.files
    assert cached.chunks == index.chunks


def test_rag_context_formats_citations(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("Repository RAG cites file lines.\n", encoding="utf-8")
    context = RepositoryRAG(tmp_path).retrieve_context("rag cites", limit=1)

    assert "README.md:1-1" in context
    assert "```" in context
