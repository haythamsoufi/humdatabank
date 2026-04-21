from flask import Blueprint

bp = Blueprint("utilities", __name__, url_prefix="/admin")

from app.routes.admin.utilities import import_export  # noqa: E402, F401
from app.routes.admin.utilities import translations  # noqa: E402, F401
from app.routes.admin.utilities import sessions  # noqa: E402, F401
from app.routes.admin.utilities import csrf  # noqa: E402, F401
