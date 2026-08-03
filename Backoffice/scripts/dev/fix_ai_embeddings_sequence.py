"""Repair ai_embeddings.id default after dump restore."""
from sqlalchemy import text

from app import create_app

app = create_app()
with app.app_context():
    from app.extensions import db

    db.session.execute(
        text(
            "ALTER TABLE ai_embeddings "
            "ALTER COLUMN id SET DEFAULT nextval('ai_embeddings_id_seq')"
        )
    )
    db.session.execute(text("ALTER SEQUENCE ai_embeddings_id_seq OWNED BY ai_embeddings.id"))
    db.session.execute(
        text(
            "SELECT setval("
            "'ai_embeddings_id_seq', "
            "GREATEST(COALESCE((SELECT MAX(id) FROM ai_embeddings), 0), 1)"
            ")"
        )
    )
    db.session.commit()

    row = db.session.execute(
        text(
            """
            SELECT column_default, pg_get_serial_sequence('ai_embeddings', 'id')
            FROM information_schema.columns
            WHERE table_name = 'ai_embeddings' AND column_name = 'id'
            """
        )
    ).fetchone()
    print("Fixed:", row)
