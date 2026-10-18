from .base import *

DEBUG = False
if SECRET_KEY == "unsafe-development-key-change-me":
    raise RuntimeError("Set a secure SECRET_KEY in the environment for production.")
if not ALLOWED_HOSTS:
    raise RuntimeError("Set ALLOWED_HOSTS for production.")
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True").lower() in ("1", "true", "yes")
