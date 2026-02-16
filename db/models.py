"""
SQLAlchemy ORM models for the RAG platform.

Uses pgvector for embedding storage and similarity search.
"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Document(Base):
    """Top-level document metadata.

    Each ingested file creates one ``Document`` row.  Related
    ``ChunkRecord`` rows reference it via ``document_id`` FK,
    enabling cascade deletes and efficient document-level queries.
    """

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_path: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(256))
    domain: Mapped[str] = mapped_column(String(64), default="maker", index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks: Mapped[list["ChunkRecord"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class ChunkRecord(Base):
    """Persisted chunk with its embedding vector."""

    __tablename__ = "chunk_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(64), index=True)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    source_path: Mapped[str] = mapped_column(String(512), index=True)
    source_name: Mapped[str] = mapped_column(String(256))
    chunk_index: Mapped[int] = mapped_column(Integer)
    token_start: Mapped[int] = mapped_column(Integer)
    token_end: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["Document | None"] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("source_path", "chunk_index", name="uq_chunk_source_index"),
        Index(
            "idx_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
