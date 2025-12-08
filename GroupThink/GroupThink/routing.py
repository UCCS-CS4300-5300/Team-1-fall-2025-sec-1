"""WebSocket URL routing configuration."""
from django.urls import re_path

from home.consumers import TranscriptionConsumer, WorkspaceChatConsumer

# All sockets
websocket_urlpatterns = [
    # Team Chat
    re_path(r"ws/workspace/(?P<workspace_id>\d+)/$", WorkspaceChatConsumer.as_asgi()),

    # Transcriptions
    re_path(r"ws/meeting/(?P<meeting_id>\d+)/$", TranscriptionConsumer.as_asgi()),
]
