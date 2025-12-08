"""Webhook handlers for recording events from JaaS."""
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.utils import timezone

from .models import Meeting, Recording


def _ts_to_dt(ts_ms):
    """Convert Jitsi ms timestamp to aware datetime (UTC)."""
    if not ts_ms:
        return None
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=dt_timezone.utc)


def handle_recording_uploaded(fqn: str, data: dict):
    """Handle the RECORDING_UPLOADED webhook event from JaaS."""
    if not fqn:
        print("RECORDING_UPLOADED with no fqn")
        return

    preauth_link = data.get("preAuthenticatedLink")
    if not preauth_link:
        print("No preAuthenticatedLink in data")
        return

    # fqn is like "appId/roomName" -> we only want the room slug
    if "/" in fqn:
        room_name = fqn.split("/", 1)[1]
    else:
        room_name = fqn

    meeting = Meeting.objects.filter(room_name=room_name).first()
    if not meeting:
        print("No Meeting found for room_name:", room_name)
        return

    duration = data.get("durationSec")
    start_ts = data.get("startTimestamp")
    end_ts = data.get("endTimestamp")
    initiator_id = data.get("initiatorId")

    expires_at = timezone.now() + timedelta(hours=24)

    rec = Recording.objects.create(
        meeting=meeting,
        storage_url=preauth_link,
        duration_sec=duration,
        started_at=_ts_to_dt(start_ts),
        ended_at=_ts_to_dt(end_ts),
        initiator_id=initiator_id or "",
        expires_at=expires_at,
    )

    meeting.recording_url = preauth_link
    meeting.save(update_fields=["recording_url"])

    print("Created Recording:", rec.id, "for meeting", meeting.id)
