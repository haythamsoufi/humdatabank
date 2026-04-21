"""Add grounding_score and confidence_level to ai_reasoning_traces if missing. Run from Backoffice: python scripts/add_ai_trace_grounding_columns.py"""
import os
from sqlalchemy import text
from app import create_app
from app.extensions import db

def main():
    app = create_app(os.getenv('FLASK_CONFIG', 'development'))
    with app.app_context():
        db.session.execute(text('''
            ALTER TABLE ai_reasoning_traces
            ADD COLUMN IF NOT EXISTS grounding_score DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS confidence_level VARCHAR(20)
        '''))
        db.session.commit()
        print('Done. grounding_score and confidence_level added if missing.')

if __name__ == '__main__':
    main()
