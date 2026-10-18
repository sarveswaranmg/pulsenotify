import os
from dotenv import load_dotenv
from pathlib import Path
from django.core.asgi import get_asgi_application

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "config.settings.local"))
application = get_asgi_application()
