"""Initial schema, PostgreSQL Row-Level Security, and pgvector extension.

Revision ID: 001_initial_pgvector
Revises: 
Create Date: 2026-10-31 01:15:00
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = '001_initial_pgvector'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Enable pgvector extension if on PostgreSQL
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Add embedding column to document_chunks if not present
    try:
        op.add_column('document_chunks', sa.Column('embedding', Vector(384), nullable=True))
    except Exception:
        pass  # Handled or already present

    # 3. Create HNSW index for fast cosine distance similarity search
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw
            ON document_chunks USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
            """
        )

        # 4. Enable Row-Level Security on sensitive tables
        from app.db.rls import TenantRLSManager
        rls_sql = TenantRLSManager.generate_rls_sql()
        op.execute(rls_sql)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw;")

    try:
        op.drop_column('document_chunks', 'embedding')
    except Exception:
        pass

