# home/consumers.py
"""WebSocket consumers for real-time chat and transcription."""
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model

from .models import WorkspaceMembership

User = get_user_model()


class WorkspaceChatConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer for workspace chat functionality."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace_id = None
        self.group_name = None

    async def connect(self):
        self.workspace_id = int(self.scope["url_route"]["kwargs"]["workspace_id"])
        self.group_name = f"workspace_{self.workspace_id}"
        user = self.scope["user"]

        if not user.is_authenticated:
            await self.close(code=4401)
            return

        is_member = await self._is_member(user, self.workspace_id)
        if not is_member:
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):  # pylint: disable=unused-argument
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # We don't send messages over WebSocket (only via POST)
        pass

    @database_sync_to_async
    def _is_member(self, user: User, workspace_id: int) -> bool:
        return WorkspaceMembership.objects.filter(
            user=user,
            workspace_id=workspace_id,
        ).exists()

    async def chat_message(self, event):
        """
        Called when group_send(..., {"type": "chat.message", ...})
        We just forward the whole event to the browser.
        """
        await self.send_json(event)


class TranscriptionConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket for live meeting transcription.

    URL: /ws/meeting/<meeting_id>/
    Group name: "meeting_<meeting_id>"
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.meeting_id = None
        self.group_name = None

    async def connect(self):
        self.meeting_id = int(self.scope["url_route"]["kwargs"]["meeting_id"])
        self.group_name = f"meeting_{self.meeting_id}"

        # If you want to require login, you can check self.scope["user"] here.
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):  # pylint: disable=unused-argument
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # We don't accept messages from clients for transcription.
        # Transcription comes only from server/webhook.
        pass

    async def transcription_chunk(self, event):
        """
        Called when group_send(..., {"type": "transcription.chunk", ...})
        """
        await self.send_json(
            {
                "type": "transcription.chunk",
                "meeting_id": event["meeting_id"],
                "text": event["text"],
                "speaker": event["speaker"],
                "timestamp": event["timestamp"],
            }
        )
