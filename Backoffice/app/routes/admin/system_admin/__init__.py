from flask import Blueprint

bp = Blueprint("system_admin", __name__, url_prefix="/admin")

from app.routes.admin.system_admin import countries  # noqa: E402, F401
from app.routes.admin.system_admin import sectors  # noqa: E402, F401
from app.routes.admin.system_admin import indicator_bank  # noqa: E402, F401
from app.routes.admin.system_admin import indicator_lookups  # noqa: E402, F401
from app.routes.admin.system_admin import lookups  # noqa: E402, F401
