"""Assignment entry-form routes.

Serves /assignment/<aes_id> — the canonical URL for data-entry assignments.
The legacy /forms/assignment/<id> route permanently redirects here.
"""
from flask import Blueprint, redirect, url_for
from flask_login import login_required

bp = Blueprint("assignments", __name__)


@bp.route("/assignment/<int:aes_id>", methods=["GET", "POST"])
@login_required
def view_assignment(aes_id):
    """Display / submit a data-entry assignment form."""
    from app.routes.forms.entry import handle_assignment_form
    return handle_assignment_form(aes_id)
