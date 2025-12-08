"""ASGI config for GroupThink project."""
import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "GroupThink.settings")

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

# Import routing AFTER django_asgi_app is created (Django must be initialized first)
import GroupThink.routing  # pylint: disable=wrong-import-position

# Main ASGI application
application = ProtocolTypeRouter(
    {
        # Handle traditional HTTP requests
        "http": django_asgi_app,
        # Handle WebSocket connections
        "websocket": AuthMiddlewareStack(
            URLRouter(GroupThink.routing.websocket_urlpatterns)
        ),
    }
)
