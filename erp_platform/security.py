# platform/security.py
from core.security_log import security_event  # noqa: F401
from core.csrf_middleware import CSRFMiddleware  # noqa: F401
from core.auth_middleware import AuthMiddleware  # noqa: F401
