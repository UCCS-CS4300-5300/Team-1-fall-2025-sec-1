# home/webhook_handlers.py
from datetime import datetime, timedelta
from django.utils import timezone

from .models import Meeting, Recording


def _ts_to_dt(ts_ms):
    """Convert Jitsi ms timestamp → aware datetime."""
    if not ts_ms:
        return None
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)


def handle_recording_uploaded(fqn: str, data: dict):
    """
    Handle JaaS RECORDING_UPLOADED webhook event.
    """
    # Check if fully qualified name is present
    if not fqn:
        print("RECORDING_UPLOADED with no fqn")
        return
    
    # Get link to recording
    preauth_link = data.get("preAuthenticatedLink")
    if not preauth_link:
        print("No preAuthenticatedLink in data")
        return

    # Attempt to split off prefix
    try:
        _, room_name = fqn.split("/", 1)
    except ValueError:
        room_name = fqn

    # Get meeting from room_name
    meeting = Meeting.objects.filter(room_name=room_name).first()
    if not meeting:
        print("No Meeting found for room_name:", room_name)
        return

    duration = data.get("durationSec")
    start_ts = data.get("startTimestamp")
    end_ts = data.get("endTimestamp")
    initiator_id = data.get("initiatorId")

    # Jaas meetings only last for 24 hours 
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

    print("Created Recording:", rec.id, "for meeting", meeting.id)
