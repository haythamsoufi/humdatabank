"""Add enriched metadata to AI documents, chunks, and embeddings

Revision ID: add_ai_doc_meta
Revises: add_fk_trace_conv
Create Date: 2026-03-05

Adds:
- ai_documents: document_date, document_language, source_organization,
                document_category, quality_score, last_verified_at
- ai_document_chunks: semantic_type, heading_hierarchy, confidence_score
- ai_embeddings: embedding_version, is_stale
- ai_reasoning_traces: grounding_score (used by Phase 3A)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_ai_doc_meta'
down_revision = 'add_fk_trace_conv'
branch_labels = None
depends_on = None


def upgrade():
    # --- ai_documents: enriched provenance ---
    with op.batch_alter_table('ai_documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('document_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('document_language', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('source_organization', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('document_category', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('quality_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('last_verified_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_ai_documents_document_date', ['document_date'])
        batch_op.create_index('ix_ai_documents_document_language', ['document_language'])
        batch_op.create_index('ix_ai_documents_document_category', ['document_category'])

    # --- ai_document_chunks: semantic richness ---
    with op.batch_alter_table('ai_document_chunks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('semantic_type', sa.String(length=50), nullable=True, server_default='paragraph'))
        batch_op.add_column(sa.Column('heading_hierarchy', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('confidence_score', sa.Float(), nullable=True))

    # --- ai_embeddings: versioning and staleness ---
    with op.batch_alter_table('ai_embeddings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('embedding_version', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('is_stale', sa.Boolean(), nullable=False, server_default='false'))

    # --- ai_reasoning_traces: grounding score (Phase 3A) ---
    with op.batch_alter_table('ai_reasoning_traces', schema=None) as batch_op:
        batch_op.add_column(sa.Column('grounding_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('confidence_level', sa.String(length=20), nullable=True))

    # --- ai_trace_reviews: expert review queue (Phase 3B) ---
    op.create_table(
        'ai_trace_reviews',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trace_id', sa.Integer(), nullable=False),
        sa.Column('reviewer_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='pending'),
        sa.Column('verdict', sa.String(length=30), nullable=True),
        sa.Column('reviewer_notes', sa.Text(), nullable=True),
        sa.Column('ground_truth_answer', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('assigned_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['trace_id'], ['ai_reasoning_traces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewer_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ai_trace_reviews_trace_id', 'ai_trace_reviews', ['trace_id'])
    op.create_index('ix_ai_trace_reviews_status', 'ai_trace_reviews', ['status'])
    op.create_index('ix_ai_trace_reviews_created_at', 'ai_trace_reviews', ['created_at'])


def downgrade():
    op.drop_index('ix_ai_trace_reviews_created_at', table_name='ai_trace_reviews')
    op.drop_index('ix_ai_trace_reviews_status', table_name='ai_trace_reviews')
    op.drop_index('ix_ai_trace_reviews_trace_id', table_name='ai_trace_reviews')
    op.drop_table('ai_trace_reviews')

    with op.batch_alter_table('ai_reasoning_traces', schema=None) as batch_op:
        batch_op.drop_column('confidence_level')
        batch_op.drop_column('grounding_score')

    with op.batch_alter_table('ai_embeddings', schema=None) as batch_op:
        batch_op.drop_column('is_stale')
        batch_op.drop_column('embedding_version')

    with op.batch_alter_table('ai_document_chunks', schema=None) as batch_op:
        batch_op.drop_column('confidence_score')
        batch_op.drop_column('heading_hierarchy')
        batch_op.drop_column('semantic_type')

    with op.batch_alter_table('ai_documents', schema=None) as batch_op:
        batch_op.drop_index('ix_ai_documents_document_category')
        batch_op.drop_index('ix_ai_documents_document_language')
        batch_op.drop_index('ix_ai_documents_document_date')
        batch_op.drop_column('last_verified_at')
        batch_op.drop_column('quality_score')
        batch_op.drop_column('document_category')
        batch_op.drop_column('source_organization')
        batch_op.drop_column('document_language')
        batch_op.drop_column('document_date')
