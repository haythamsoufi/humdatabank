"""Debug script to check DB schema and table visibility."""
import os
os.environ['FLASK_CONFIG'] = 'testing'

from app import create_app, db
from sqlalchemy import text

app = create_app('testing')

print("=== Starting DB diagnostic ===")
with app.app_context():
    print("Inside app context #1")
    
    with db.engine.connect() as conn:
        sp = conn.execute(text('SHOW search_path')).scalar()
        cs = conn.execute(text('SELECT current_schema()')).scalar()
        print(f"search_path: {sp}")
        print(f"current_schema: {cs}")
    
    # Drop and recreate
    db.metadata.drop_all(bind=db.engine, checkfirst=True)
    db.metadata.create_all(bind=db.engine, checkfirst=True)
    
    # Check table visibility from engine
    with db.engine.connect() as conn:
        r = conn.execute(text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='user')")).scalar()
        print(f"user table exists (engine.connect): {r}")
    
    # Now try via db.session  
    print("Trying db.session query...")
    try:
        r2 = db.session.execute(text("SELECT 1 FROM \"user\" LIMIT 0")).fetchall()
        print(f"user table accessible via db.session: True")
    except Exception as e:
        print(f"user table NOT accessible via db.session: {e}")
    
    # Try nested context
    print("Opening nested app context...")
    with app.app_context():
        print("Inside nested app context #2")
        try:
            r3 = db.session.execute(text("SELECT 1 FROM \"user\" LIMIT 0")).fetchall()
            print(f"user table accessible in nested context: True")
        except Exception as e:
            print(f"user table NOT accessible in nested context: {e}")

print("=== Done ===")
