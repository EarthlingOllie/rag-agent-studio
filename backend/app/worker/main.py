"""Worker and Beat entrypoint: `celery -A app.worker.main worker|beat`.

Settings are validated on import, so a misconfigured worker exits before it connects.
"""

from app.core.settings import load_settings
from app.worker.celery_app import configure_celery

app = configure_celery(load_settings())
