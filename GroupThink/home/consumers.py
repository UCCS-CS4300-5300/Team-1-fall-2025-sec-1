"""WebSocket consumers for real-time communication."""
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model

from .models import WorkspaceMembership

User = get_user_model()


class WorkspaceChatConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer for workspace team chat."""

    workspace_id: int
    group_name: str

    async def connect(self):
        """Handle WebSocket connection for workspace chat."""
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

    async def disconnect(self, _close_code):
        """Handle WebSocket disconnection."""
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        """Handle incoming JSON messages (not used - messages sent via POST)."""

    @database_sync_to_async
    def _is_member(self, user, workspace_id: int) -> bool:
        """Check if user is a member of the workspace."""
        return WorkspaceMembership.objects.filter(
            user=user,
            workspace_id=workspace_id,
        ).exists()

    async def chat_message(self, event):
        """Forward chat messages to the browser."""
        await self.send_json(event)


class TranscriptionConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer for live meeting transcription."""

    meeting_id: int
    group_name: str

    async def connect(self):
        """Handle WebSocket connection for transcription."""
        self.meeting_id = int(self.scope["url_route"]["kwargs"]["meeting_id"])
        self.group_name = f"meeting_{self.meeting_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, _close_code):
        """Handle WebSocket disconnection."""
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        """Handle incoming JSON (not used - transcription comes from webhook)."""

    async def transcription_chunk(self, event):
        """Send transcription chunk to client."""
        await self.send_json(
            {
                "type": "transcription.chunk",
                "meeting_id": event["meeting_id"],
                "text": event["text"],
                "speaker": event["speaker"],
                "timestamp": event["timestamp"],
            }
        )
