# GroupThink/home/meeting_ai.py
import os
import datetime as dt
from django.conf import settings
from django.db import transaction
from anthropic import Anthropic
from .models import Meeting, MeetingTranscriptChunk, Task

# ---------------- Anthropic client (lazy init) ----------------

_client: Anthropic | None = None

def get_client() -> Anthropic:
    """
    Return a cached Anthropic client.
    Raises a clear error if ANTHROPIC_API_KEY isn't configured.
    """
    global _client
    if _client is not None:
        return _client

    api_key = getattr(settings, "ANTHROPIC_API_KEY", "") or os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured. "
            "Set it in your .env or hosting environment."
        )

    _client = Anthropic(api_key=api_key)
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


# ---------------- Transcript → Tasks via AI ----------------

def extract_tasks_from_meeting(meeting_id: int, created_by_user_id: int) -> dict:
    """
    Parse meeting transcript into tasks via Claude, create Task rows.
    Returns {"created": <int>, "reason": <str optional>}.
    """
    meeting = Meeting.objects.get(id=meeting_id)
    transcript_text = _assemble_transcript_text(meeting)
    if not transcript_text:
        return {"created": 0, "reason": "Transcript is empty."}

    prompt = f"""{SYSTEM_TASKS}

Transcript:
{transcript_text}

Return a JSON object with this exact structure:
{TASK_SCHEMA}"""

    try:
        resp = get_client().messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        # Extract text from response
        response_text = resp.content[0].text
        
        # Parse JSON from response
        import json
        # Sometimes Claude wraps JSON in markdown code blocks, so clean it
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        data = json.loads(response_text)
    except Exception as e:
        return {"created": 0, "reason": f"Failed to parse AI response: {e}"}

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
                pass

        Task.objects.create(
            title=title[:200],
            description=(item.get("notes") or "").strip(),
            workspace=meeting.workspace,
            assigned_to=None,  # TODO: map assignee_free_text -> User
            created_by_id=created_by_user_id,
            status="todo",
            due_date=due,
            is_personal=False,
        )
        created += 1

    if created == 0:
        return {"created": 0, "reason": "No tasks were extracted from the transcript."}
    return {"created": created}