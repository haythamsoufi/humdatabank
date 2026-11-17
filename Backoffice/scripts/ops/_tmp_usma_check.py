from sqlalchemy import text

from app import create_app, db

app = create_app()
with app.app_context():
    versions = db.session.execute(
        text(
            "SELECT id, template_id, name, status FROM form_template_version "
            "WHERE name = 'US Macro Awards' ORDER BY id"
        )
    ).fetchall()
    print("versions", versions)
    if versions:
        version_id = versions[-1][0]
        template_id = versions[-1][1]
        counts = db.session.execute(
            text(
                """
                SELECT item_type, COUNT(*)
                FROM form_item
                WHERE version_id = :vid AND archived = false
                GROUP BY item_type
                ORDER BY item_type
                """
            ),
            {"vid": version_id},
        ).fetchall()
        sections = db.session.execute(
            text(
                "SELECT name FROM form_section WHERE version_id = :vid AND archived = false ORDER BY \"order\""
            ),
            {"vid": version_id},
        ).fetchall()
        projects = db.session.execute(
            text(
                "SELECT reference, title FROM project WHERE portfolio = 'US Macro Awards' ORDER BY reference"
            )
        ).fetchall()
        print("template", template_id, "items", counts)
        print("sections", [row[0] for row in sections])
        print("projects", len(projects))
        for row in projects:
            print(" ", row[0], row[1])
