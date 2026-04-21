# Backward-compat shim -- moved to app.middleware.security_headers
from app.middleware.security_headers import *  # noqa: F401,F403
from app.middleware.security_headers import init_security_headers  # noqa: F401
