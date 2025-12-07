import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "GroupThink.settings")

# Set up Django
django.setup()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application

import GroupThink.routing

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "GroupThink.settings")

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

