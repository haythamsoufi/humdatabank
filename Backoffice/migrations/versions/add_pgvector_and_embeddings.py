"""add pgvector extension and AI embeddings tables

Revision ID: add_pgvector_embeddings
Revises: add_ai_chat_archiving
Create Date: 2026-01-16 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_pgvector_embeddings'
down_revision = 'rename_year_to_period'
branch_labels = None
depends_on = None

_PGVECTOR_HINT = (
    "PostgreSQL must have the pgvector extension installed. "
    "On Fly.io unmanaged Postgres (ifrc-db-dev), use Dockerfile.db with "
    "FROM pgvector/pgvector:pg15 and redeploy the DB app. See FLY_DEPLOYMENT.md."
)


def upgrade():
    # Enable pgvector extension (requires Postgres image with pgvector, e.g. pgvector/pgvector:pg15)
    try:
        op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    except Exception as e:
        err = str(e).lower()
        if "extension" in err and "vector" in err and ("not available" in err or "no such file" in err):
            raise RuntimeError(
                f"pgvector extension is not installed on this PostgreSQL server. {_PGVECTOR_HINT}"
            ) from e
        raise

    # Create ai_documents table
    op.create_table('ai_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('submitted_document_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('filename', sa.String(length=500), nullable=False),
        sa.Column('file_type', sa.String(length=50), nullable=False),
        sa.Column('file_size_bytes', sa.Integer(), nullable=True),
        sa.Column('storage_path', sa.String(length=1000), nullable=True),
        sa.Column('content_hash', sa.String(length=64), nullable=True),
        sa.Column('processing_status', sa.String(length=50), nullable=False),
        sa.Column('processing_error', sa.Text(), nullable=True),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('total_chunks', sa.Integer(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.Column('total_pages', sa.Integer(), nullable=True),
        sa.Column('embedding_model', sa.String(length=100), nullable=True),
        sa.Column('embedding_dimensions', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=True),
        sa.Column('allowed_roles', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('searchable', sa.Boolean(), nullable=True),
        sa.Column('extra_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['submitted_document_id'], ['submitted_document.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ai_documents_content_hash', 'ai_documents', ['content_hash'], unique=False)
    op.create_index('ix_ai_documents_is_public', 'ai_documents', ['is_public'], unique=False)
    op.create_index('ix_ai_documents_processing_status', 'ai_documents', ['processing_status'], unique=False)
    op.create_index('ix_ai_documents_searchable', 'ai_documents', ['searchable'], unique=False)
    op.create_index('ix_ai_documents_submitted_document_id', 'ai_documents', ['submitted_document_id'], unique=False)
    op.create_index('ix_ai_documents_user_id', 'ai_documents', ['user_id'], unique=False)

    # Create ai_document_chunks table
    op.create_table('ai_document_chunks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('content_length', sa.Integer(), nullable=False),
        sa.Column('token_count', sa.Integer(), nullable=True),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=True),
        sa.Column('section_title', sa.String(length=500), nullable=True),
        sa.Column('chunk_type', sa.String(length=50), nullable=False),
        sa.Column('overlap_with_previous', sa.Integer(), nullable=True),
        sa.Column('extra_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['ai_documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ai_document_chunks_document_id', 'ai_document_chunks', ['document_id'], unique=False)

    # Create ai_embeddings table with pgvector column
    op.create_table('ai_embeddings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('chunk_id', sa.Integer(), nullable=False),
        sa.Column('embedding', postgresql.ARRAY(sa.Float()), nullable=False),  # Will be converted to vector type below
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('dimensions', sa.Integer(), nullable=False),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.Column('generation_cost_usd', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['chunk_id'], ['ai_document_chunks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['ai_documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ai_embeddings_chunk_id', 'ai_embeddings', ['chunk_id'], unique=True)
    op.create_index('ix_ai_embeddings_document_id', 'ai_embeddings', ['document_id'], unique=False)

    # Change embedding column to vector type
    op.execute('ALTER TABLE ai_embeddings ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector(1536)')

    # Create vector index for cosine similarity search
    # Using ivfflat index for approximate nearest neighbor search
    op.execute("""
        CREATE INDEX idx_ai_embeddings_vector_cosine
        ON ai_embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)

    # Create ai_reasoning_traces table
    op.create_table('ai_reasoning_traces',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.String(length=100), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('query_language', sa.String(length=10), nullable=True),
        sa.Column('agent_mode', sa.String(length=50), nullable=False),
        sa.Column('max_iterations', sa.Integer(), nullable=True),
        sa.Column('actual_iterations', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('steps', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('tools_used', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('tool_call_count', sa.Integer(), nullable=True),
        sa.Column('total_input_tokens', sa.Integer(), nullable=True),
        sa.Column('total_output_tokens', sa.Integer(), nullable=True),
        sa.Column('total_cost_usd', sa.Float(), nullable=True),
        sa.Column('execution_time_ms', sa.Integer(), nullable=True),
        sa.Column('final_answer', sa.Text(), nullable=True),
        sa.Column('llm_provider', sa.String(length=50), nullable=True),
        sa.Column('llm_model', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ai_reasoning_traces_conversation_id', 'ai_reasoning_traces', ['conversation_id'], unique=False)
    op.create_index('ix_ai_reasoning_traces_created_at', 'ai_reasoning_traces', ['created_at'], unique=False)
    op.create_index('ix_ai_reasoning_traces_status', 'ai_reasoning_traces', ['status'], unique=False)
    op.create_index('ix_ai_reasoning_traces_user_id', 'ai_reasoning_traces', ['user_id'], unique=False)

    # Create ai_tool_usage table
    op.create_table('ai_tool_usage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trace_id', sa.Integer(), nullable=True),
        sa.Column('tool_name', sa.String(length=100), nullable=False),
        sa.Column('tool_input', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('tool_output', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('execution_time_ms', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['trace_id'], ['ai_reasoning_traces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ai_tool_usage_created_at', 'ai_tool_usage', ['created_at'], unique=False)
    op.create_index('ix_ai_tool_usage_success', 'ai_tool_usage', ['success'], unique=False)
    op.create_index('ix_ai_tool_usage_tool_name', 'ai_tool_usage', ['tool_name'], unique=False)
    op.create_index('ix_ai_tool_usage_trace_id', 'ai_tool_usage', ['trace_id'], unique=False)
    op.create_index('ix_ai_tool_usage_user_id', 'ai_tool_usage', ['user_id'], unique=False)


def downgrade():
    # Drop tables in reverse order
    op.drop_table('ai_tool_usage')
    op.drop_table('ai_reasoning_traces')
    op.drop_table('ai_embeddings')
    op.drop_table('ai_document_chunks')
    op.drop_table('ai_documents')

    # Drop pgvector extension
    op.execute('DROP EXTENSION IF EXISTS vector')
