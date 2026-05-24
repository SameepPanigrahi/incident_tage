from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from src.config import Settings
from src.rag.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)

# Regex matching common log timestamp prefixes
# e.g. "2024-01-15 10:30:45" or "2024-01-15T10:30:45.123Z"
LOG_TS_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}",
    re.MULTILINE,
)


class IncidentDataIngester:
    """Ingest runbooks, past-incident reports, and raw logs into ChromaDB.

    Key design choice: logs use a **log-aware chunker** that splits on
    timestamp boundaries so individual log entries are never torn apart.
    """

    def __init__(self, vector_store: ChromaVectorStore, settings: Settings) -> None:
        self.vs = vector_store
        self.settings = settings
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            separators=["\n## ", "\n### ", "\n\n", "\n", " "],
        )

    # ── Runbooks (.md) ───────────────────────────────────────────

    def ingest_runbooks(self, directory: str | Path) -> int:
        """Read every .md file, chunk semantically, store with metadata."""
        directory = Path(directory)
        if not directory.exists():
            logger.warning("Runbook directory not found: %s", directory)
            return 0

        docs: list[Document] = []
        for md_file in sorted(directory.glob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            chunks = self._splitter.split_text(text)
            for i, chunk in enumerate(chunks):
                docs.append(
                    Document(
                        page_content=chunk,
                        metadata={
                            "source": md_file.name,
                            "doc_type": "runbook",
                            "chunk_index": i,
                        },
                    )
                )
        if docs:
            lc_store = self.vs.get_langchain_store()
            lc_store.add_documents(docs)
            logger.info("Ingested %d runbook chunks from %s", len(docs), directory)
        return len(docs)

    # ── Past incidents (.json) ───────────────────────────────────

    def ingest_past_incidents(self, directory: str | Path) -> int:
        """Read .json incident reports, flatten to text, store."""
        directory = Path(directory)
        if not directory.exists():
            logger.warning("Past-incidents directory not found: %s", directory)
            return 0

        docs: list[Document] = []
        for jf in sorted(directory.glob("*.json")):
            incident = json.loads(jf.read_text(encoding="utf-8"))

            # Flatten JSON into a human-readable text block
            text_parts = [
                f"Incident ID: {incident.get('incident_id', 'N/A')}",
                f"Title: {incident.get('title', 'N/A')}",
                f"Date: {incident.get('date', 'N/A')}",
                f"Severity: {incident.get('severity', 'N/A')}",
                f"Duration: {incident.get('duration_minutes', 'N/A')} minutes",
                f"Impacted Services: {', '.join(incident.get('impacted_services', []))}",
                f"Root Cause: {incident.get('root_cause', 'N/A')}",
                f"Resolution: {incident.get('resolution', 'N/A')}",
            ]
            lessons = incident.get("lessons_learned", [])
            if lessons:
                text_parts.append("Lessons Learned:")
                for ll in lessons:
                    text_parts.append(f"- {ll}")

            tags = incident.get("tags", [])
            if tags:
                text_parts.append(f"Tags: {', '.join(tags)}")

            timeline = incident.get("timeline", [])
            if timeline:
                text_parts.append("Timeline:")
                for entry in timeline:
                    text_parts.append(
                        f"  [{entry.get('timestamp', '')}] {entry.get('event', '')}"
                    )

            full_text = "\n".join(text_parts)
            chunks = self._splitter.split_text(full_text)
            for i, chunk in enumerate(chunks):
                docs.append(
                    Document(
                        page_content=chunk,
                        metadata={
                            "source": jf.name,
                            "doc_type": "past_incident",
                            "incident_id": incident.get("incident_id", ""),
                            "chunk_index": i,
                        },
                    )
                )
        if docs:
            lc_store = self.vs.get_langchain_store()
            lc_store.add_documents(docs)
            logger.info("Ingested %d past-incident chunks from %s", len(docs), directory)
        return len(docs)

    # ── Logs (.log) ──────────────────────────────────────────────

    def _log_aware_chunker(self, text: str, chunk_size: int | None = None) -> list[str]:
        """Split log text respecting entry boundaries.

        Strategy:
        1. Split the text on lines that start with a timestamp.
        2. Each split = one log entry (may be multi-line for stack traces).
        3. Group consecutive entries until the chunk exceeds *chunk_size*.
        """
        chunk_size = chunk_size or self.settings.CHUNK_SIZE
        lines = text.split("\n")

        entries: list[str] = []
        current_entry_lines: list[str] = []

        for line in lines:
            if LOG_TS_RE.match(line) and current_entry_lines:
                entries.append("\n".join(current_entry_lines))
                current_entry_lines = [line]
            else:
                current_entry_lines.append(line)
        if current_entry_lines:
            entries.append("\n".join(current_entry_lines))

        # Group entries into chunks
        chunks: list[str] = []
        current_chunk: list[str] = []
        current_len = 0

        for entry in entries:
            entry_len = len(entry)
            if current_len + entry_len > chunk_size and current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = [entry]
                current_len = entry_len
            else:
                current_chunk.append(entry)
                current_len += entry_len

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        return chunks

    def ingest_logs(self, directory: str | Path) -> int:
        """Read .log files with log-aware chunking, store with metadata."""
        directory = Path(directory)
        if not directory.exists():
            logger.warning("Log directory not found: %s", directory)
            return 0

        docs: list[Document] = []
        for log_file in sorted(directory.glob("*.log")):
            text = log_file.read_text(encoding="utf-8")
            chunks = self._log_aware_chunker(text)
            for i, chunk in enumerate(chunks):
                docs.append(
                    Document(
                        page_content=chunk,
                        metadata={
                            "source": log_file.name,
                            "doc_type": "log",
                            "chunk_index": i,
                        },
                    )
                )
        if docs:
            lc_store = self.vs.get_langchain_store()
            lc_store.add_documents(docs)
            logger.info("Ingested %d log chunks from %s", len(docs), directory)
        return len(docs)

    # ── Convenience ──────────────────────────────────────────────

    def ingest_all(self, data_dir: str | Path) -> dict[str, int]:
        """Ingest everything under *data_dir* and return counts."""
        data_dir = Path(data_dir)
        counts = {
            "runbooks": self.ingest_runbooks(data_dir / "runbooks"),
            "past_incidents": self.ingest_past_incidents(data_dir / "past_incidents"),
            # "logs": self.ingest_logs(data_dir / "incident_logs"),
        }
        logger.info("Ingestion complete: %s", counts)
        return counts
