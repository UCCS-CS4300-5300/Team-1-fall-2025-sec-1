import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .recording_webhook_handlers import _ts_to_dt, handle_recording_uploaded

from home.models import (
    Meeting,
    MeetingTranscriptChunk,
    Recording,
)

User = get_user_model()

class BaseWebhookTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alice",
            email="alice@example.com",
            password="testpass123",
        )
        # minimal meeting; workspace/created_by are optional
        self.meeting = Meeting.objects.create(
            title="Test Meeting",
            room_name="groupthink-room-123",
        )

    def post_webhook(self, payload: dict):
        return self.client.post(
            "/webhooks/jaas/",
            data=json.dumps(payload),
            content_type="application/json",
        )


class TranscriptWebhookTests(BaseWebhookTestCase):
    def test_transcription_chunk_creates_meeting_chunk(self):
        """
        When TRANSCRIPTION_CHUNK_RECEIVED is sent for an existing meeting,
        a MeetingTranscriptChunk should be created with the correct text + speaker.
        """
        payload = {
            "eventType": "TRANSCRIPTION_CHUNK_RECEIVED",
            "fqn": f"vpaas-magic-cookie/{self.meeting.room_name}",
            "data": {
                "final": "Hello world from webhook",
                "participant": {"name": "Alice"},
            },
        }

        resp = self.post_webhook(payload)
        self.assertEqual(resp.status_code, 200)

        chunks = MeetingTranscriptChunk.objects.filter(meeting=self.meeting)
        self.assertEqual(chunks.count(), 1)
        chunk = chunks.first()
        self.assertEqual(chunk.text, "Hello world from webhook")
        self.assertEqual(chunk.speaker, "Alice")

    def test_transcription_chunk_uses_roomName_when_fqn_missing(self):
        """
        Room slug should still resolve when only roomName is present in data.
        """
        payload = {
            "eventType": "TRANSCRIPTION_CHUNK_RECEIVED",
            "data": {
                "roomName": f"vpaas-magic-cookie/{self.meeting.room_name}",
                "final": "Using roomName instead of fqn",
                "participant": {"id": "speaker-123"},
            },
        }

        resp = self.post_webhook(payload)
        self.assertEqual(resp.status_code, 200)

        chunks = MeetingTranscriptChunk.objects.filter(meeting=self.meeting)
        self.assertEqual(chunks.count(), 1)
        chunk = chunks.first()
        self.assertEqual(chunk.text, "Using roomName instead of fqn")
        # falls back to participant.id
        self.assertEqual(chunk.speaker, "speaker-123")

    def test_transcription_chunk_does_not_create_when_meeting_missing(self):
        """
        If the meeting isn't found for the slug, no chunk should be created.
        """
        payload = {
            "eventType": "TRANSCRIPTION_CHUNK_RECEIVED",
            "fqn": "vpaas-magic-cookie/nonexistent-room",
            "data": {
                "final": "This should not be saved",
                "participant": {"name": "Ghost"},
            },
        }

        resp = self.post_webhook(payload)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(MeetingTranscriptChunk.objects.count(), 0)

    def test_transcription_chunk_ignored_when_text_is_empty(self):
        """
        If there's no text (final/stable/text), nothing should be saved.
        """
        payload = {
            "eventType": "TRANSCRIPTION_CHUNK_RECEIVED",
            "fqn": f"vpaas-magic-cookie/{self.meeting.room_name}",
            "data": {
                "final": "   ",  # whitespace only
                "participant": {"name": "Alice"},
            },
        }

        resp = self.post_webhook(payload)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(MeetingTranscriptChunk.objects.count(), 0)


class GetTranscriptViewTests(BaseWebhookTestCase):
    def test_get_transcript_returns_plain_text_with_speakers(self):
        """
        get_transcript should return 'Speaker: text' lines in created_at order.
        """
        # Two chunks in order
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            text="Hello there",
            speaker="Alice",
        )
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            text="Second line",
            speaker="",  # will become "Unknown"
        )

        url = reverse("get_transcript", args=[self.meeting.room_name])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/plain")

        body = resp.content.decode("utf-8").splitlines()
        self.assertEqual(body[0], "Alice: Hello there")
        self.assertEqual(body[1], "Unknown: Second line")

    def test_get_transcript_404_for_missing_meeting(self):
        url = reverse("get_transcript", args=["nonexistent-room"])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)


class RecordingWebhookTests(BaseWebhookTestCase):
    def test_recording_uploaded_creates_recording_and_updates_meeting(self):
        """
        When RECORDING_UPLOADED is received, a Recording row should be created
        and Meeting.recording_url should be updated.
        """
        preauth_link = "https://example.com/recording.mp4"
        payload = {
            "eventType": "RECORDING_UPLOADED",
            "fqn": f"vpaas-magic-cookie/{self.meeting.room_name}",
            "data": {
                "preAuthenticatedLink": preauth_link,
                "durationSec": 42,
                "startTimestamp": 1700000000000,  # ms
                "endTimestamp": 1700000042000,
                "initiatorId": "jaas-user-1",
            },
        }

        resp = self.post_webhook(payload)
        self.assertEqual(resp.status_code, 200)

        # Recording created
        self.assertEqual(Recording.objects.count(), 1)
        rec = Recording.objects.first()
        self.assertEqual(rec.meeting, self.meeting)
        self.assertEqual(rec.storage_url, preauth_link)
        self.assertEqual(rec.duration_sec, 42)
        self.assertEqual(rec.initiator_id, "jaas-user-1")
        self.assertFalse(rec.is_expired())  # should be ~24h from now

        # Meeting updated
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.recording_url, preauth_link)

    def test_recording_uploaded_no_meeting_does_not_create(self):
        """
        If the room slug cannot be matched to a Meeting, no Recording is created.
        """
        payload = {
            "eventType": "RECORDING_UPLOADED",
            "fqn": "vpaas-magic-cookie/unknown-room",
            "data": {
                "preAuthenticatedLink": "https://example.com/other.mp4",
                "durationSec": 5,
            },
        }

        resp = self.post_webhook(payload)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Recording.objects.count(), 0)


class MyRecordingsViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user1 = User.objects.create_user(
            username="user1", email="u1@example.com", password="pw"
        )
        self.user2 = User.objects.create_user(
            username="user2", email="u2@example.com", password="pw"
        )

        self.meeting1 = Meeting.objects.create(
            title="User1 meeting",
            room_name="room-user1",
        )
        self.meeting2 = Meeting.objects.create(
            title="User2 meeting",
            room_name="room-user2",
        )

        # participants
        self.meeting1.participants.add(self.user1)
        self.meeting2.participants.add(self.user2)

        # recordings
        now = timezone.now()
        self.rec1 = Recording.objects.create(
            meeting=self.meeting1,
            storage_url="https://example.com/u1.mp4",
            duration_sec=10,
            started_at=now - timedelta(minutes=2),
            ended_at=now - timedelta(minutes=1),
            initiator_id="u1",
            expires_at=now + timedelta(hours=24),
        )
        self.rec2 = Recording.objects.create(
            meeting=self.meeting2,
            storage_url="https://example.com/u2.mp4",
            duration_sec=20,
            started_at=now - timedelta(minutes=4),
            ended_at=now - timedelta(minutes=3),
            initiator_id="u2",
            expires_at=now + timedelta(hours=24),
        )

    def test_my_recordings_shows_only_recordings_for_meetings_user_participated_in(self):
        self.client.login(username="user1", password="pw")
        resp = self.client.get(reverse("my_recordings"))
        self.assertEqual(resp.status_code, 200)

        recordings = list(resp.context["recordings"])
        self.assertEqual(len(recordings), 1)
        self.assertEqual(recordings[0], self.rec1)
        self.assertEqual(recordings[0].meeting, self.meeting1)

    def test_my_recordings_empty_when_no_participation(self):
        # new user not in any participants
        User = get_user_model()
        user3 = User.objects.create_user(
            username="user3", email="u3@example.com", password="pw"
        )
        self.client.login(username="user3", password="pw")
        resp = self.client.get(reverse("my_recordings"))
        self.assertEqual(resp.status_code, 200)
        recordings = list(resp.context["recordings"])
        self.assertEqual(len(recordings), 0)

class RecordingHandlerUnitTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="edgeuser", email="edge@example.com", password="pw"
        )
        self.meeting = Meeting.objects.create(
            title="Edge Meeting",
            room_name="edge-room",
        )

    def test_handle_recording_uploaded_no_fqn_does_nothing(self):
        """
        If fqn is empty/None, handle_recording_uploaded should return early
        and not create any Recording rows.
        """
        data = {
            "preAuthenticatedLink": "https://example.com/edge.mp4",
            "durationSec": 10,
        }

        handle_recording_uploaded("", data)
        self.assertEqual(Recording.objects.count(), 0)

        handle_recording_uploaded(None, data)
        self.assertEqual(Recording.objects.count(), 0)

    def test_handle_recording_uploaded_missing_link_does_nothing(self):
        """
        If preAuthenticatedLink is missing from data, it should not create a Recording.
        """
        fqn = f"vpaas-magic-cookie/{self.meeting.room_name}"

        # No preAuthenticatedLink key at all
        data = {
            "durationSec": 10,
            "startTimestamp": None,
            "endTimestamp": None,
        }

        handle_recording_uploaded(fqn, data)
        self.assertEqual(Recording.objects.count(), 0)

    def test_ts_to_dt_returns_none_for_falsy_timestamp(self):
        """
        _ts_to_dt should gracefully return None for falsy timestamps.
        This hits the early-return branch.
        """
        self.assertIsNone(_ts_to_dt(None))
        self.assertIsNone(_ts_to_dt(0))
