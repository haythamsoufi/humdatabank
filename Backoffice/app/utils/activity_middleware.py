# Backward-compat shim -- moved to app.middleware.activity_middleware
from app.middleware.activity_middleware import *  # noqa: F401,F403
from app.middleware.activity_middleware import init_activity_tracking, track_admin_action  # noqa: F401
