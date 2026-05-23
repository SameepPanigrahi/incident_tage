from __future__ import annotations

import logging
from pathlib import Path

import chromadb
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

from src.config import Settings
import httpx
http_client = httpx.Client(verify=False)

logger = logging.getLogger(__name__)


class ChromaVectorStore:
    """Manages a ChromaDB persistent collection with LangChain wrappers.

    Usage::

        store = ChromaVectorStore(settings)
        retriever = store.get_retriever()
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.persist_dir = Path(settings.CHROMA_PERSIST_DIR)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        # Persistent ChromaDB client
        self._client = chromadb.PersistentClient(
            path=str(self.persist_dir)
        )
        self.collection_name = settings.COLLECTION_NAME

        # Default embedding function
        self._embedding_fn = OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            openai_api_key=settings.OPENAI_API_KEY,
            http_client=http_client
        )
        logger.info(
            "ChromaVectorStore initialised — collection=%s  dir=%s",
            self.collection_name,
            self.persist_dir,
        )

    # ── Collection helpers ────────────────────────────────────────

    def get_or_create_collection(self) -> chromadb.Collection:
        """Return (or create) the raw ChromaDB collection."""
        return self._client.get_or_create_collection(
            name=self.collection_name
        )

    def get_langchain_store(self) -> Chroma:
        """Return a LangChain Chroma wrapper for add_documents / similarity_search."""
        return Chroma(
            client=self._client,
            collection_name=self.collection_name,
            embedding_function=self._embedding_fn,
        )

    def get_retriever(self, top_k: int | None = None):
        """Return a LangChain retriever backed by this collection."""
        k = top_k or self.settings.TOP_K
        lc_store = self.get_langchain_store()
        return lc_store.as_retriever(search_kwargs={"k": k})

    # ── Ops ──────────────────────────────────────────────────────

    def health_check(self) -> dict:
        """Return basic health info about the vector store."""
        col = self.get_or_create_collection()
        return {
            "status": "healthy",
            "collection": self.collection_name,
            "document_count": col.count(),
            "persist_directory": str(self.persist_dir),
        }

    def reset_collection(self) -> None:
        """Delete and recreate the collection (useful for re-ingestion)."""
        self._client.delete_collection(self.collection_name)
        logger.warning("Collection %s deleted and recreated.", self.collection_name)
