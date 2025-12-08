# GroupThink/home/meeting_ai.py
"""AI-powered task extraction from meeting transcripts."""
import datetime as dt
import json
import os
import traceback

from django.conf import settings
from django.db import connection

from anthropic import Anthropic

from .models import Meeting, Task, UserProfile


# ---------------- Anthropic client (lazy init) ----------------

_client: Anthropic | None = None


def get_client() -> Anthropic:
    """
    Return a cached Anthropic client.
    Raises a clear error if ANTHROPIC_API_KEY isn't configured.
    """
    global _client  # pylint: disable=global-statement
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
    "Use concise titles. Identify the assignee if explicitly mentioned or clearly implied. "
    "Leave assignee empty only if truly unassigned or unclear. "
    "Only set due_date if explicitly stated. "
    "Return strictly valid JSON per the provided schema."
)


# ---------------- Helpers ----------------

def _assemble_transcript_text(meeting: Meeting) -> str:
    """Assemble full transcript text from meeting chunks."""
    parts = []
    for chunk in meeting.chunks.order_by("created_at").only("speaker", "text"):
        prefix = f"{chunk.speaker}: " if chunk.speaker else ""
        parts.append(prefix + (chunk.text or "").strip())
    return "\n".join(parts).strip()


def _get_meeting_participants(meeting: Meeting) -> list[dict]:
    """
    Get list of workspace members who could be assigned tasks.
    Returns list of dicts with user info for matching.
    """
    members = meeting.workspace.memberships.select_related('user', 'user__profile').all()

    participants = []
    for membership in members:
        user = membership.user
        # Try to get display name from profile, fall back to username
        try:
            display_name = user.profile.display_name
        except UserProfile.DoesNotExist:
            display_name = user.username

        participants.append({
            'user': user,
            'display_name': display_name,
            'username': user.username,
        })

    return participants


def _find_user_by_name(name: str, participants: list[dict]):
    """
    Find user from participant list by name.
    Matches against display_name or username.
    """
    if not name:
        return None

    name_lower = name.lower().strip()

    for participant in participants:
        if participant['display_name'].lower() == name_lower:
            return participant['user']
        if participant['username'].lower() == name_lower:
            return participant['user']

    return None


def _parse_ai_response(response_text: str) -> dict:
    """Parse AI response text, handling markdown code blocks."""
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0].strip()
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0].strip()
    return json.loads(response_text)


def _create_task_from_item(item: dict, meeting: Meeting, participants: list[dict],
                           created_by_user_id: int) -> bool:
    """Create a Task from an AI-extracted item. Returns True if created."""
    title = (item.get("title") or "").strip()
    if not title:
        return False

    assignee_text = (item.get("assignee") or "").strip()
    assigned_user = _find_user_by_name(assignee_text, participants)

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
        assigned_to=assigned_user,
        created_by_id=created_by_user_id,
        status="todo",
        due_date=due,
        is_personal=False,
    )
    return True


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

    # Get workspace members as potential assignees
    participants = _get_meeting_participants(meeting)
    participant_names = [p['display_name'] for p in participants]
    participant_list = ", ".join(participant_names) if participant_names else "No participants"

    system_prompt = (
        "Extract concrete, actionable tasks from the transcript. "
        "Use concise titles. Identify the assignee if explicitly mentioned or clearly implied. "
        f"Valid assignees are: {participant_list}. "
        "Use the exact name from the list. Leave assignee empty if truly unassigned or unclear. "
        "Only set due_date if explicitly stated. "
        "Return strictly valid JSON per the provided schema."
    )

    prompt = f"""{system_prompt}

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

        response_text = resp.content[0].text
        data = _parse_ai_response(response_text)
    except (json.JSONDecodeError, KeyError, IndexError, AttributeError) as err:
        return {"created": 0, "reason": f"Failed to parse AI response: {err}"}

    items = data.get("tasks", []) if isinstance(data, dict) else []
    created = sum(
        1 for item in items
        if _create_task_from_item(item, meeting, participants, created_by_user_id)
    )

    if created == 0:
        return {"created": 0, "reason": "No tasks were extracted from the transcript."}
    return {"created": created}


def extract_tasks_from_meeting_threaded(meeting_id: int, created_by_user_id: int) -> None:
    """
    Wrapper for extract_tasks_from_meeting that closes DB connections properly.
    Designed to run in a background thread.
    """
    try:
        result = extract_tasks_from_meeting(meeting_id, created_by_user_id)
        print(f"[THREAD] Task extraction completed: {result}")
    except Exception as err:  # pylint: disable=broad-exception-caught
        print(f"[THREAD] Task extraction failed: {err}")
        print(traceback.format_exc())
    finally:
        # CRITICAL: Close database connections in this thread
        # Django's DB connections are thread-local and must be closed
        connection.close()
