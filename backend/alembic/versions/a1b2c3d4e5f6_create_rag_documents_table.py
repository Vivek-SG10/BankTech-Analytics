"""create_rag_documents_table

Revision ID: a1b2c3d4e5f6
Revises: b06b2df5d0d7
Create Date: 2026-11-11 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'b06b2df5d0d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'rag_documents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('file_type', sa.String(10), nullable=False),
        sa.Column('file_size_bytes', sa.Integer(), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('uploaded_by', sa.String(36), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('access_level', sa.String(20), nullable=False, server_default='all'),
        sa.Column('chunk_count', sa.Integer(), nullable=True),
        sa.Column('indexed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
    )
    op.create_index('ix_rag_documents_content_hash', 'rag_documents', ['content_hash'], unique=True)
    op.create_index('ix_rag_documents_status', 'rag_documents', ['status'])


def downgrade() -> None:
    op.drop_index('ix_rag_documents_status', 'rag_documents')
    op.drop_index('ix_rag_documents_content_hash', 'rag_documents')
    op.drop_table('rag_documents')
