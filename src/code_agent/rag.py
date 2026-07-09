from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from code_agent.config import agent_dir
from code_agent.context import EXCLUDED_NAMES


INDEX_VERSION = 1
DEFAULT_CHUNK_LINES = 80
DEFAULT_CHUNK_OVERLAP = 10
DEFAULT_MAX_FILE_BYTES = 1_000_000
SENSITIVE_NAMES = {".env", ".env.local", ".env.production", ".env.development"}


class FileMetadata(BaseModel):
    path: str
    size: int
    mtime_ns: int


class RepoChunk(BaseModel):
    path: str
    start_line: int
    end_line: int
    text: str

    @property
    def citation(self) -> str:
        return f"{self.path}:{self.start_line}-{self.end_line}"


class RepositoryIndex(BaseModel):
    version: int = INDEX_VERSION
    root: str
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    files: list[FileMetadata] = Field(default_factory=list)
    chunks: list[RepoChunk] = Field(default_factory=list)


class RetrievedChunk(BaseModel):
    chunk: RepoChunk
    score: float


class RepositoryRAG:
    def __init__(
        self,
        root: Path,
        *,
        cache_path: Path | None = None,
        chunk_lines: int = DEFAULT_CHUNK_LINES,
        overlap: int = DEFAULT_CHUNK_OVERLAP,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    ) -> None:
        self.root = root.resolve()
        self.cache_path = cache_path or agent_dir(self.root) / "rag_index.json"
        self.chunk_lines = chunk_lines
        self.overlap = overlap
        self.max_file_bytes = max_file_bytes

    def index(self, *, force: bool = False) -> RepositoryIndex:
        files = self._scan_files()
        if not force:
            cached = self._load_cache()
            if cached and cached.version == INDEX_VERSION and cached.root == str(self.root) and cached.files == files:
                return cached

        chunks: list[RepoChunk] = []
        for metadata in files:
            chunks.extend(self._chunk_file(self.root / metadata.path))
        index = RepositoryIndex(root=str(self.root), files=files, chunks=chunks)
        self._save_cache(index)
        return index

    def retrieve(self, query: str, *, limit: int = 6) -> list[RetrievedChunk]:
        terms = Counter(_tokenize(query))
        if not terms:
            return []
        results: list[RetrievedChunk] = []
        for chunk in self.index().chunks:
            score = _score_chunk(chunk, terms)
            if score > 0:
                results.append(RetrievedChunk(chunk=chunk, score=score))
        return sorted(results, key=lambda item: (-item.score, item.chunk.path, item.chunk.start_line))[:limit]

    def retrieve_context(self, query: str, *, limit: int = 6) -> str:
        retrieved = self.retrieve(query, limit=limit)
        if not retrieved:
            return ""
        parts = [
            "Use the following repository excerpts when relevant. Cite them as `path:start-end`.",
        ]
        for index, item in enumerate(retrieved, start=1):
            chunk = item.chunk
            parts.extend(
                [
                    "",
                    f"[{index}] {chunk.citation}",
                    "```",
                    chunk.text,
                    "```",
                ]
            )
        return "\n".join(parts)

    def _load_cache(self) -> RepositoryIndex | None:
        if not self.cache_path.exists():
            return None
        try:
            return RepositoryIndex.model_validate(json.loads(self.cache_path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError, ValueError):
            return None

    def _save_cache(self, index: RepositoryIndex) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(index.model_dump_json(indent=2) + "\n", encoding="utf-8")

    def _scan_files(self) -> list[FileMetadata]:
        files: list[FileMetadata] = []
        for path in sorted(self.root.rglob("*"), key=lambda item: item.relative_to(self.root).as_posix().lower()):
            if not path.is_file():
                continue
            rel = path.relative_to(self.root)
            if _is_ignored(rel):
                continue
            if path.name in SENSITIVE_NAMES:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_size > self.max_file_bytes or _looks_binary(path):
                continue
            files.append(FileMetadata(path=rel.as_posix(), size=stat.st_size, mtime_ns=stat.st_mtime_ns))
        return files

    def _chunk_file(self, path: Path) -> list[RepoChunk]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        lines = text.splitlines()
        if not lines:
            return []
        rel = path.relative_to(self.root).as_posix()
        chunks: list[RepoChunk] = []
        step = max(self.chunk_lines - self.overlap, 1)
        start = 0
        while start < len(lines):
            end = min(start + self.chunk_lines, len(lines))
            selected = lines[start:end]
            chunks.append(
                RepoChunk(
                    path=rel,
                    start_line=start + 1,
                    end_line=end,
                    text="\n".join(selected),
                )
            )
            if end == len(lines):
                break
            start += step
        return chunks


def _is_ignored(relative_path: Path) -> bool:
    return any(part in EXCLUDED_NAMES for part in relative_path.parts)


def _looks_binary(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:4096]
    except OSError:
        return True
    return b"\0" in sample


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9_]{2,}", text)]


def _score_chunk(chunk: RepoChunk, query_terms: Counter[str]) -> float:
    text_terms = Counter(_tokenize(chunk.text))
    path_terms = Counter(_tokenize(chunk.path.replace("/", " ")))
    score = 0.0
    for term, query_count in query_terms.items():
        if term in text_terms:
            score += min(text_terms[term], query_count) * 1.0
        if term in path_terms:
            score += min(path_terms[term], query_count) * 2.5
    return score
