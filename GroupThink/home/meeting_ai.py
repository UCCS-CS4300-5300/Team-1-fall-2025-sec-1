# GroupThink/home/meeting_ai.py
import io
import datetime as dt
from django.conf import settings
from django.db import transaction
from openai import OpenAI
from .models import Meeting, MeetingTranscriptChunk, Task

from .models import Meeting, MeetingTranscriptChunk, Task

# ---------------- OpenAI client (lazy init) ----------------

_client: OpenAI | None = None

def get_client() -> OpenAI:
    """
    Return a cached OpenAI client.
    Raises a clear error if OPENAI_API_KEY isn't configured.
    """
    global _client
    if _client is not None:
        return _client

    api_key = getattr(settings, "OPENAI_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. "
            "Set it in your .env or hosting environment."
        )

    _client = OpenAI(api_key=api_key)
    return _client


# ---------------- JSON schema for AI-produced tasks ----------------

TASK_SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "assignee": {"type": "string"},
                    "due_date": {
                        "type": "string",
                        "description": "YYYY-MM-DD or empty",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", ""],
                    },
                    "notes": {"type": "string"},
                },
                "required": ["title"],
            },
        }
    },
    "required": ["tasks"],
}

SYSTEM_TASKS = (
    "Extract concrete, actionable tasks from the transcript. "
    "Use concise titles. Only set assignee or due_date if explicitly stated; "
    "otherwise leave them blank. Return strictly valid JSON per the provided schema."
)


# ---------------- Helpers ----------------

def _assemble_transcript_text(meeting: Meeting) -> str:
    parts = []
    for c in meeting.chunks.order_by("created_at").only("speaker", "text"):
        prefix = f"{c.speaker}: " if c.speaker else ""
        parts.append(prefix + (c.text or "").strip())
    return "\n".join(parts).strip()


# ---------------- Audio → transcript (optional) ----------------

def transcribe_meeting(meeting_id: int) -> int:
    """
    Transcribe the meeting's audio and store into MeetingTranscriptChunk rows.
    Requires either meeting.audio_file (FileField) OR meeting.recording_url.
    Returns number of chunks saved.
    """
    meeting = Meeting.objects.select_for_update().get(id=meeting_id)

    # prefer a FileField if you added it
    audio_fp = None
    if hasattr(meeting, "audio_file") and meeting.audio_file:
        audio_fp = meeting.audio_file.open("rb")
    elif meeting.recording_url:
        # fallback: fetch from URL into memory
        import requests
        r = requests.get(meeting.recording_url, timeout=60)
        r.raise_for_status()
        audio_fp = io.BytesIO(r.content)
    else:
        raise ValueError("No audio available. Upload an audio file or set recording_url.")

    with audio_fp:
        tr = get_client().audio.transcriptions.create(
            model="whisper-1",  # or "gpt-4o-transcribe" depending on your account
            file=audio_fp,
            response_format="verbose_json",  # gives segments with timestamps
        )

    segments = getattr(tr, "segments", None) or []
    created = 0
    with transaction.atomic():
        # optional: clear old chunks
        meeting.chunks.all().delete()
        for seg in segments:
            MeetingTranscriptChunk.objects.create(
                meeting=meeting,
                text=(seg.get("text") or "").strip(),
                speaker="",  # add diarization later if you have it
            )
            created += 1

    return created


# ---------------- Transcript → Tasks via AI ----------------

def extract_tasks_from_meeting(meeting_id: int, created_by_user_id: int) -> dict:
    """
    Parse meeting transcript into tasks via structured output, create Task rows.
    Returns {"created": <int>, "reason": <str optional>}.
    """
    meeting = Meeting.objects.get(id=meeting_id)
    transcript_text = _assemble_transcript_text(meeting)
    if not transcript_text:
        return {"created": 0, "reason": "Transcript is empty."}

    resp = get_client().responses.create(
        model="gpt-4.1-mini",  # or "gpt-4.1" / "gpt-4o" / "gpt-5" if you have it
        input=[
            {"role": "system", "content": SYSTEM_TASKS},
            {"role": "user", "content": f"Transcript:\n{transcript_text}"},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "meeting_tasks",
                "schema": TASK_SCHEMA,
                "strict": True,
            },
        },
    )

    # New Responses API: structured output lives in .output[0].content[0].parsed
    try:
        data = resp.output[0].content[0].parsed
    except Exception:
        return {"created": 0, "reason": "Failed to parse AI response."}

    items = data.get("tasks", []) if isinstance(data, dict) else []
    created = 0

    for item in items:
        title = (item.get("title") or "").strip()
        if not title:
            continue

        assignee_free_text = (item.get("assignee") or "").strip()  # not used yet

        due = None
        raw_due = (item.get("due_date") or "").strip()
        if raw_due:
            try:
                due = dt.date.fromisoformat(raw_due)
            except ValueError:
                # ignore bad dates; leave due_date as None
                pass

        Task.objects.create(
            title=title[:200],
            description=(item.get("notes") or "").strip(),
            workspace=meeting.workspace,      # tie to the meeting's workspace
            assigned_to=None,                 # TODO: map assignee_free_text -> User
            created_by_id=created_by_user_id,
            status="todo",
            due_date=due,
            is_personal=False,
        )
        created += 1

    if created == 0:
        return {"created": 0, "reason": "No tasks were extracted from the transcript."}
    return {"created": created}
