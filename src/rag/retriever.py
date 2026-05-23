from __future__ import annotations

import logging
from typing import Any

from langchain_core.documents import Document

from src.config import Settings
from src.rag.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)


class IncidentRetriever:
    """Domain-aware retriever that builds targeted queries for each agent.

    Instead of generic similarity search, each method constructs a query
    tuned for its purpose (root cause research vs. remediation lookup)
    and optionally filters by ``doc_type`` metadata.
    """

    def __init__(self, vector_store: ChromaVectorStore, settings: Settings) -> None:
        self.vs = vector_store
        self.settings = settings
        self._lc_store = vector_store.get_langchain_store()

    # ── Generic retrieve ─────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        filter_type: str | None = None,
        top_k: int | None = None,
    ) -> list[Document]:
        """Run similarity search, optionally filtering by doc_type.

        Args:
            query: Natural language query.
            filter_type: One of ``runbook``, ``past_incident``, ``log``.
            top_k: Override the default TOP_K.

        Returns:
            List of LangChain ``Document`` objects.
        """
        k = top_k or self.settings.TOP_K
        search_kwargs: dict[str, Any] = {"k": k}
        if filter_type:
            search_kwargs["filter"] = {"doc_type": filter_type}

        docs = self._lc_store.similarity_search(query, **search_kwargs)
        logger.info(
            "Retrieved %d docs for query (filter=%s): %.80s...",
            len(docs), filter_type, query,
        )
        return docs

    # ── Root-cause-specific retrieval ─────────────────────────────

    def retrieve_for_root_cause(
        self,
        error_patterns: list[str],
        services: list[str],
    ) -> tuple[str, list[str]]:
        """Build a targeted query from error patterns & impacted services.

        Returns:
            (formatted_context, list_of_source_filenames)
        """
        query_parts = [
            "Root cause analysis for errors:",
            *[f"  - {p}" for p in error_patterns[:5]],
            "Impacted services: " + ", ".join(services),
        ]
        query = "".join(query_parts)

        # Search runbooks + past incidents
        runbook_docs = self.retrieve(query, filter_type="runbook", top_k=3)
        incident_docs = self.retrieve(query, filter_type="past_incident", top_k=3)
        all_docs = runbook_docs + incident_docs

        context = self._format_context(all_docs)
        sources = list({d.metadata.get("source", "unknown") for d in all_docs})
        return context, sources

    # ── Remediation-specific retrieval ────────────────────────────

    def retrieve_for_remediation(
        self,
        root_causes: list[dict],
    ) -> tuple[str, list[str]]:
        """Build a query from identified root causes to find fix procedures.

        Returns:
            (formatted_context, list_of_source_filenames)
        """
        cause_descriptions = [
            rc.get("cause", rc.get("category", "unknown")) for rc in root_causes
        ]
        query = (
            "Remediation steps and runbook procedures for: "
            + "; ".join(cause_descriptions)
        )
        docs = self.retrieve(query, filter_type="runbook", top_k=5)
        context = self._format_context(docs)
        sources = list({d.metadata.get("source", "unknown") for d in docs})
        return context, sources

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _format_context(documents: list[Document]) -> str:
        """Format retrieved documents into an LLM-friendly string with citations."""
        if not documents:
            return "No relevant context found in the knowledge base."

        parts: list[str] = []
        for i, doc in enumerate(documents, 1):
            source = doc.metadata.get("source", "unknown")
            doc_type = doc.metadata.get("doc_type", "unknown")
            parts.append(
                f"--- [Source {i}: {source} (type: {doc_type})] ---\n"
                f"{doc.page_content}\n"
            )
        return "\n".join(parts)
