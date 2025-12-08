"""Tests for AI-powered transcript task extraction."""
import json
import threading
import time
from datetime import date, timedelta
from unittest import skipIf
from unittest.mock import Mock, call, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from home.meeting_ai import _assemble_transcript_text, extract_tasks_from_meeting, get_client
from home.models import (
    Meeting,
    MeetingTranscriptChunk,
    Task,
    UserProfile,
    Workspace,
    WorkspaceMembership,
)

User = get_user_model()

class MeetingTranscriptChunkTestCase(TestCase):
    """Test MeetingTranscriptChunk model"""

    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='TestPass123')
        self.profile1 = UserProfile.objects.create(user=self.user1, display_name='User One')
        
        self.workspace = Workspace.objects.create(name='Test Team', created_by=self.user1)
        WorkspaceMembership.objects.create(user=self.user1, workspace=self.workspace, role='admin')
        
        self.meeting = Meeting.objects.create(
            title='Test Meeting',
            room_name='test-room-123',
            created_by=self.user1,
            workspace=self.workspace,
            status='ended',
            started_at=timezone.now(),
            ended_at=timezone.now()
        )

    def test_create_transcript_chunk(self):
        """Test creating a transcript chunk"""
        chunk = MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='We need to implement the login feature.'
        )
        
        self.assertEqual(chunk.meeting, self.meeting)
        self.assertEqual(chunk.speaker, 'User One')
        self.assertEqual(chunk.text, 'We need to implement the login feature.')

    def test_transcript_chunk_ordering(self):
        """Test that transcript chunks are ordered by created_at"""
        chunk1 = MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='First message'
        )
        chunk2 = MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User Two',
            text='Second message'
        )
        chunk3 = MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='Third message'
        )
        
        chunks = list(self.meeting.chunks.order_by('created_at'))
        self.assertEqual(chunks[0].text, 'First message')
        self.assertEqual(chunks[1].text, 'Second message')
        self.assertEqual(chunks[2].text, 'Third message')

    def test_transcript_chunk_without_speaker(self):
        """Test creating transcript chunk without speaker"""
        chunk = MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='',  # Empty string, not None
            text='System message or unattributed text'
        )
        
        self.assertEqual(chunk.speaker, '')
        self.assertEqual(chunk.text, 'System message or unattributed text')


class AssembleTranscriptTestCase(TestCase):
    """Test transcript assembly from chunks"""

    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='TestPass123')
        self.profile1 = UserProfile.objects.create(user=self.user1, display_name='User One')
        
        self.workspace = Workspace.objects.create(name='Test Team', created_by=self.user1)
        
        self.meeting = Meeting.objects.create(
            title='Test Meeting',
            room_name='test-room-123',
            created_by=self.user1,
            workspace=self.workspace
        )

    def test_assemble_simple_transcript(self):
        """Test assembling transcript from multiple chunks"""
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='Hello everyone'
        )
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User Two',
            text='Hi there'
        )
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='Let\'s discuss the project'
        )
        
        transcript = _assemble_transcript_text(self.meeting)
        
        expected = "User One: Hello everyone\nUser Two: Hi there\nUser One: Let's discuss the project"
        self.assertEqual(transcript, expected)

    def test_assemble_transcript_without_speaker(self):
        """Test assembling transcript with chunks that have no speaker"""
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='Hello'
        )
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='',  # Empty string instead of None
            text='System notification'
        )
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User Two',
            text='Hi'
        )
        
        transcript = _assemble_transcript_text(self.meeting)
        
        expected = "User One: Hello\nSystem notification\nUser Two: Hi"
        self.assertEqual(transcript, expected)

    def test_assemble_empty_transcript(self):
        """Test assembling transcript with no chunks"""
        transcript = _assemble_transcript_text(self.meeting)
        self.assertEqual(transcript, "")

    def test_assemble_transcript_strips_whitespace(self):
        """Test that transcript assembly strips whitespace"""
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='  Hello with spaces  '
        )
        
        transcript = _assemble_transcript_text(self.meeting)
        self.assertEqual(transcript, "User One: Hello with spaces")


class ExtractTasksFromMeetingTestCase(TestCase):
    """Test AI task extraction from meeting transcripts"""

    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='TestPass123')
        self.profile1 = UserProfile.objects.create(user=self.user1, display_name='User One')
        self.user2 = User.objects.create_user(username='user2', password='TestPass123')
        self.profile2 = UserProfile.objects.create(user=self.user2, display_name='User Two')
        
        self.workspace = Workspace.objects.create(name='Test Team', created_by=self.user1)
        WorkspaceMembership.objects.create(user=self.user1, workspace=self.workspace, role='admin')
        WorkspaceMembership.objects.create(user=self.user2, workspace=self.workspace, role='member')
        
        self.meeting = Meeting.objects.create(
            title='Test Meeting',
            room_name='test-room-123',
            created_by=self.user1,
            workspace=self.workspace,
            status='ended'
        )

    @patch('home.meeting_ai.get_client')
    def test_extract_tasks_creates_task_objects(self, mock_get_client):
        """Test that extract_tasks_from_meeting creates Task objects"""
        # Setup transcript
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='We need to implement the login feature by next Friday.'
        )
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User Two',
            text='I can work on that.'
        )
        
        # Mock Anthropic API response
        mock_response = Mock()
        mock_response.content = [Mock(text=json.dumps({
            "tasks": [
                {
                    "title": "Implement login feature",
                    "assignee": "User Two",
                    "due_date": "",
                    "priority": "high",
                    "notes": "Create login functionality with authentication"
                }
            ]
        }))]
        
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        # Execute
        result = extract_tasks_from_meeting(self.meeting.id, self.user1.id)
        
        # Verify
        self.assertEqual(result['created'], 1)
        task = Task.objects.get(title='Implement login feature')
        self.assertEqual(task.workspace, self.workspace)
        self.assertEqual(task.created_by, self.user1)
        self.assertEqual(task.status, 'todo')
        self.assertFalse(task.is_personal)

    @patch('home.meeting_ai.get_client')
    def test_extract_tasks_with_multiple_tasks(self, mock_get_client):
        """Test extracting multiple tasks from transcript"""
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='We need to implement login and write tests.'
        )
        
        mock_response = Mock()
        mock_response.content = [Mock(text=json.dumps({
            "tasks": [
                {
                    "title": "Implement login feature",
                    "assignee": "",
                    "due_date": "",
                    "priority": "high",
                    "notes": ""
                },
                {
                    "title": "Write unit tests",
                    "assignee": "",
                    "due_date": "",
                    "priority": "medium",
                    "notes": ""
                },
                {
                    "title": "Deploy to staging",
                    "assignee": "",
                    "due_date": "",
                    "priority": "low",
                    "notes": ""
                }
            ]
        }))]
        
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        result = extract_tasks_from_meeting(self.meeting.id, self.user1.id)
        
        self.assertEqual(result['created'], 3)
        self.assertEqual(Task.objects.filter(workspace=self.workspace).count(), 3)

    def test_extract_tasks_empty_transcript(self):
        """Test extracting tasks from empty transcript"""
        result = extract_tasks_from_meeting(self.meeting.id, self.user1.id)
        
        self.assertEqual(result['created'], 0)
        self.assertIn('reason', result)
        self.assertEqual(result['reason'], 'Transcript is empty.')

    @patch('home.meeting_ai.get_client')
    def test_extract_tasks_with_due_date(self, mock_get_client):
        """Test extracting tasks with due dates"""
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='Complete this by December 31st, 2025.'
        )
        
        future_date = (date.today() + timedelta(days=30)).isoformat()
        
        mock_response = Mock()
        mock_response.content = [Mock(text=json.dumps({
            "tasks": [
                {
                    "title": "Complete project",
                    "assignee": "",
                    "due_date": future_date,
                    "priority": "",
                    "notes": ""
                }
            ]
        }))]
        
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        result = extract_tasks_from_meeting(self.meeting.id, self.user1.id)
        
        self.assertEqual(result['created'], 1)
        task = Task.objects.first()
        self.assertIsNotNone(task.due_date)
        self.assertEqual(task.due_date.isoformat(), future_date)

    @patch('home.meeting_ai.get_client')
    def test_extract_tasks_handles_invalid_due_date(self, mock_get_client):
        """Test that invalid due dates are handled gracefully"""
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='Do this soon.'
        )
        
        mock_response = Mock()
        mock_response.content = [Mock(text=json.dumps({
            "tasks": [
                {
                    "title": "Complete task",
                    "assignee": "",
                    "due_date": "invalid-date-format",
                    "priority": "",
                    "notes": ""
                }
            ]
        }))]
        
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        result = extract_tasks_from_meeting(self.meeting.id, self.user1.id)
        
        self.assertEqual(result['created'], 1)
        task = Task.objects.first()
        self.assertIsNone(task.due_date)

    @patch('home.meeting_ai.get_client')
    def test_extract_tasks_with_markdown_wrapped_json(self, mock_get_client):
        """Test that JSON wrapped in markdown code blocks is handled"""
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='We need to build a new feature.'
        )
        
        # Simulate Claude wrapping JSON in markdown
        mock_response = Mock()
        mock_response.content = [Mock(text='```json\n' + json.dumps({
            "tasks": [
                {
                    "title": "Build new feature",
                    "assignee": "",
                    "due_date": "",
                    "priority": "",
                    "notes": ""
                }
            ]
        }) + '\n```')]
        
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        result = extract_tasks_from_meeting(self.meeting.id, self.user1.id)
        
        self.assertEqual(result['created'], 1)

    @patch('home.meeting_ai.get_client')
    def test_extract_tasks_handles_api_error(self, mock_get_client):
        """Test handling of API errors"""
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='Create a task.'
        )
        
        mock_client = Mock()
        mock_client.messages.create.side_effect = Exception('API Error')
        mock_get_client.return_value = mock_client
        
        result = extract_tasks_from_meeting(self.meeting.id, self.user1.id)
        
        self.assertEqual(result['created'], 0)
        self.assertIn('reason', result)
        self.assertIn('Failed to parse AI response', result['reason'])

    @patch('home.meeting_ai.get_client')
    def test_extract_tasks_skips_empty_titles(self, mock_get_client):
        """Test that tasks with empty titles are skipped"""
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='Some discussion.'
        )
        
        mock_response = Mock()
        mock_response.content = [Mock(text=json.dumps({
            "tasks": [
                {
                    "title": "",
                    "assignee": "",
                    "due_date": "",
                    "priority": "",
                    "notes": "This has no title"
                },
                {
                    "title": "Valid task",
                    "assignee": "",
                    "due_date": "",
                    "priority": "",
                    "notes": ""
                }
            ]
        }))]
        
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        result = extract_tasks_from_meeting(self.meeting.id, self.user1.id)
        
        self.assertEqual(result['created'], 1)
        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(Task.objects.first().title, 'Valid task')

    @patch('home.meeting_ai.get_client')
    def test_extract_tasks_truncates_long_titles(self, mock_get_client):
        """Test that titles longer than 200 characters are truncated"""
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='Very long task description.'
        )
        
        long_title = "A" * 250  # 250 character title
        
        mock_response = Mock()
        mock_response.content = [Mock(text=json.dumps({
            "tasks": [
                {
                    "title": long_title,
                    "assignee": "",
                    "due_date": "",
                    "priority": "",
                    "notes": ""
                }
            ]
        }))]
        
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        result = extract_tasks_from_meeting(self.meeting.id, self.user1.id)
        
        self.assertEqual(result['created'], 1)
        task = Task.objects.first()
        self.assertEqual(len(task.title), 200)

    @patch('home.meeting_ai.get_client')
    def test_extract_tasks_sets_correct_workspace(self, mock_get_client):
        """Test that tasks are associated with the correct workspace"""
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='Create a task.'
        )
        
        mock_response = Mock()
        mock_response.content = [Mock(text=json.dumps({
            "tasks": [
                {
                    "title": "Workspace task",
                    "assignee": "",
                    "due_date": "",
                    "priority": "",
                    "notes": ""
                }
            ]
        }))]
        
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        result = extract_tasks_from_meeting(self.meeting.id, self.user1.id)
        
        task = Task.objects.first()
        self.assertEqual(task.workspace, self.workspace)
        self.assertFalse(task.is_personal)

    @patch('home.meeting_ai.get_client')
    def test_extract_tasks_no_tasks_extracted(self, mock_get_client):
        """Test response when no tasks are extracted"""
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='Just casual conversation, no tasks.'
        )
        
        mock_response = Mock()
        mock_response.content = [Mock(text=json.dumps({
            "tasks": []
        }))]
        
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        result = extract_tasks_from_meeting(self.meeting.id, self.user1.id)
        
        self.assertEqual(result['created'], 0)
        self.assertEqual(result['reason'], 'No tasks were extracted from the transcript.')

    @patch('home.meeting_ai.get_client')
    def test_extract_tasks_preserves_description(self, mock_get_client):
        """Test that task descriptions (notes) are preserved"""
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='We need to refactor the authentication system.'
        )
        
        mock_response = Mock()
        mock_response.content = [Mock(text=json.dumps({
            "tasks": [
                {
                    "title": "Refactor authentication",
                    "assignee": "",
                    "due_date": "",
                    "priority": "",
                    "notes": "Improve security and add 2FA support"
                }
            ]
        }))]
        
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        result = extract_tasks_from_meeting(self.meeting.id, self.user1.id)
        
        self.assertEqual(result['created'], 1)
        task = Task.objects.first()
        self.assertEqual(task.description, 'Improve security and add 2FA support')

    @patch('home.meeting_ai.get_client')
    def test_extract_tasks_assigned_to_is_none(self, mock_get_client):
        """Test that assigned_to is None when no assignee is specified"""
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='Someone should work on this.'
        )
        
        mock_response = Mock()
        mock_response.content = [Mock(text=json.dumps({
            "tasks": [
                {
                    "title": "Unassigned task",
                    "assignee": "",
                    "due_date": "",
                    "priority": "",
                    "notes": ""
                }
            ]
        }))]
        
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        result = extract_tasks_from_meeting(self.meeting.id, self.user1.id)
        
        task = Task.objects.first()
        self.assertIsNone(task.assigned_to)

    @patch('home.meeting_ai.get_client')
    def test_extract_tasks_handles_plain_markdown_blocks(self, mock_get_client):
        """Test that JSON wrapped in plain markdown blocks (without json tag) is handled"""
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='Create a new task.'
        )
        
        # Simulate Claude wrapping JSON in plain markdown
        mock_response = Mock()
        mock_response.content = [Mock(text='```\n' + json.dumps({
            "tasks": [
                {
                    "title": "New task",
                    "assignee": "",
                    "due_date": "",
                    "priority": "",
                    "notes": ""
                }
            ]
        }) + '\n```')]
        
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        result = extract_tasks_from_meeting(self.meeting.id, self.user1.id)
        
        self.assertEqual(result['created'], 1)

    @patch('home.meeting_ai.get_client')
    def test_extract_tasks_calls_anthropic_with_correct_model(self, mock_get_client):
        """Test that the correct Claude model is used"""
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='Create a task.'
        )
        
        mock_response = Mock()
        mock_response.content = [Mock(text=json.dumps({"tasks": []}))]
        
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        extract_tasks_from_meeting(self.meeting.id, self.user1.id)
        
        # Verify the correct model was used
        call_args = mock_client.messages.create.call_args
        self.assertEqual(call_args[1]['model'], 'claude-sonnet-4-20250514')

    @patch('home.meeting_ai.get_client')
    def test_extract_tasks_uses_max_tokens(self, mock_get_client):
        """Test that max_tokens is set correctly"""
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='Create a task.'
        )
        
        mock_response = Mock()
        mock_response.content = [Mock(text=json.dumps({"tasks": []}))]
        
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        extract_tasks_from_meeting(self.meeting.id, self.user1.id)
        
        # Verify max_tokens
        call_args = mock_client.messages.create.call_args
        self.assertEqual(call_args[1]['max_tokens'], 2000)


class GetClientTestCase(TestCase):
    """Test the Anthropic client initialization"""

    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key-123'})
    @patch('home.meeting_ai.Anthropic')
    def test_get_client_creates_client_with_api_key(self, mock_anthropic):
        """Test that get_client creates Anthropic client with API key"""
        # Clear cached client
        import home.meeting_ai
        home.meeting_ai._client = None
        
        get_client()
        
        mock_anthropic.assert_called_once_with(api_key='test-key-123')

    @patch.dict('os.environ', {}, clear=True)
    @patch('home.meeting_ai.settings')
    def test_get_client_raises_error_without_api_key(self, mock_settings):
        """Test that get_client raises error when API key is missing"""
        # Clear cached client
        import home.meeting_ai
        home.meeting_ai._client = None
        
        # Mock settings without API key
        mock_settings.ANTHROPIC_API_KEY = ""
        
        with self.assertRaises(RuntimeError) as context:
            get_client()
        
        self.assertIn('ANTHROPIC_API_KEY is not configured', str(context.exception))

    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key-123'})
    @patch('home.meeting_ai.Anthropic')
    def test_get_client_caches_client(self, mock_anthropic):
        """Test that get_client caches the client instance"""
        # Clear cached client
        import home.meeting_ai
        home.meeting_ai._client = None
        
        # Call 
        
        client1 = get_client()
        client2 = get_client()
        
        # Should only create once
        self.assertEqual(mock_anthropic.call_count, 1)
        self.assertEqual(client1, client2)

class ExtractTasksFromMeetingThreadedTestCase(TestCase):
    """Test threaded AI task extraction from meeting transcripts"""

    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='TestPass123')
        self.profile1 = UserProfile.objects.create(user=self.user1, display_name='User One')
        self.user2 = User.objects.create_user(username='user2', password='TestPass123')
        self.profile2 = UserProfile.objects.create(user=self.user2, display_name='User Two')
        
        self.workspace = Workspace.objects.create(name='Test Team', created_by=self.user1)
        WorkspaceMembership.objects.create(user=self.user1, workspace=self.workspace, role='admin')
        WorkspaceMembership.objects.create(user=self.user2, workspace=self.workspace, role='member')
        
        self.meeting = Meeting.objects.create(
            title='Test Meeting',
            room_name='test-room-123',
            created_by=self.user1,
            workspace=self.workspace,
            status='ended'
        )

    @patch('home.meeting_ai.get_client')
    @patch('home.meeting_ai.connection')
    def test_threaded_extraction_closes_connection(self, mock_connection, mock_get_client):
        """Test that database connection is closed after threaded execution"""
        from home.meeting_ai import extract_tasks_from_meeting_threaded
        
        # Setup transcript
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='We need to implement the login feature.'
        )
        
        # Mock Anthropic API response
        mock_response = Mock()
        mock_response.content = [Mock(text=json.dumps({
            "tasks": [
                {
                    "title": "Implement login feature",
                    "assignee": "",
                    "due_date": "",
                    "priority": "",
                    "notes": ""
                }
            ]
        }))]
        
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        # Execute in thread
        thread = threading.Thread(
            target=extract_tasks_from_meeting_threaded,
            args=(self.meeting.id, self.user1.id),
            daemon=True
        )
        thread.start()
        thread.join(timeout=5)  # Wait up to 5 seconds
        
        # Verify connection.close() was called
        mock_connection.close.assert_called_once()
    @skipIf(
        'sqlite' in settings.DATABASES['default']['ENGINE'],
        "SQLite doesn't handle concurrent writes well in tests"
    )
    @patch('home.meeting_ai.get_client')
    def test_threaded_extraction_creates_tasks(self, mock_get_client):
        """Test that threaded extraction successfully creates tasks"""
        from home.meeting_ai import extract_tasks_from_meeting_threaded
        
        # Setup transcript
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='We need to build feature A and feature B.'
        )
        
        # Mock Anthropic API response
        mock_response = Mock()
        mock_response.content = [Mock(text=json.dumps({
            "tasks": [
                {
                    "title": "Build feature A",
                    "assignee": "",
                    "due_date": "",
                    "priority": "",
                    "notes": ""
                },
                {
                    "title": "Build feature B",
                    "assignee": "",
                    "due_date": "",
                    "priority": "",
                    "notes": ""
                }
            ]
        }))]
        
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        # Execute in thread
        thread = threading.Thread(
            target=extract_tasks_from_meeting_threaded,
            args=(self.meeting.id, self.user1.id),
            daemon=True
        )
        thread.start()
        thread.join(timeout=5)
        
        # Wait a bit for database writes
        time.sleep(0.1)
        
        # Verify tasks were created
        self.assertEqual(Task.objects.filter(workspace=self.workspace).count(), 2)
        self.assertTrue(Task.objects.filter(title='Build feature A').exists())
        self.assertTrue(Task.objects.filter(title='Build feature B').exists())

    @patch('home.meeting_ai.get_client')
    @patch('home.meeting_ai.connection')
    def test_threaded_extraction_handles_exception(self, mock_connection, mock_get_client):
        """Test that exceptions are handled and connection is still closed"""
        from home.meeting_ai import extract_tasks_from_meeting_threaded
        
        # Setup transcript
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='Create a task.'
        )
        
        # Make API call raise an exception
        mock_client = Mock()
        mock_client.messages.create.side_effect = Exception('API Error')
        mock_get_client.return_value = mock_client
        
        # Execute in thread
        thread = threading.Thread(
            target=extract_tasks_from_meeting_threaded,
            args=(self.meeting.id, self.user1.id),
            daemon=True
        )
        thread.start()
        thread.join(timeout=5)
        
        # Verify connection.close() was still called despite exception
        mock_connection.close.assert_called_once()
        
        # Verify no tasks were created
        self.assertEqual(Task.objects.count(), 0)

    @patch('home.meeting_ai.get_client')
    def test_threaded_extraction_with_empty_transcript(self, mock_get_client):
        """Test threaded extraction with empty transcript"""
        from home.meeting_ai import extract_tasks_from_meeting_threaded
        
        # No transcript chunks created
        
        # Execute in thread
        thread = threading.Thread(
            target=extract_tasks_from_meeting_threaded,
            args=(self.meeting.id, self.user1.id),
            daemon=True
        )
        thread.start()
        thread.join(timeout=5)
        
        # Should complete without error, no tasks created
        self.assertEqual(Task.objects.count(), 0)

    def test_threaded_extraction_returns_none(self):
        """Test that threaded function returns None (fire-and-forget)"""
        from home.meeting_ai import extract_tasks_from_meeting_threaded
        
        result = extract_tasks_from_meeting_threaded(self.meeting.id, self.user1.id)
        
        # Function should return None since it's designed for threading
        self.assertIsNone(result)


class GenerateTasksFromMeetingViewTestCase(TestCase):
    """Test the generate_tasks_from_meeting view with threading"""

    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(username='user1', password='TestPass123')
        self.profile1 = UserProfile.objects.create(user=self.user1, display_name='User One')
        
        self.workspace = Workspace.objects.create(name='Test Team', created_by=self.user1)
        WorkspaceMembership.objects.create(user=self.user1, workspace=self.workspace, role='admin')
        
        self.meeting = Meeting.objects.create(
            title='Test Meeting',
            room_name='test-room-123',
            created_by=self.user1,
            workspace=self.workspace,
            status='ended'
        )
        
        # Add some transcript
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='We need to implement new features.'
        )

    @patch('home.views.threading.Thread')
    def test_view_starts_thread(self, mock_thread_class):
        """Test that the view starts a thread for task generation"""
        mock_thread = Mock()
        mock_thread_class.return_value = mock_thread
        
        self.client.login(username='user1', password='TestPass123')
        
        response = self.client.post(
            reverse('generate_tasks_from_meeting', args=[self.meeting.id])
        )
        
        # Verify thread was created
        mock_thread_class.assert_called_once()
        call_kwargs = mock_thread_class.call_args[1]
        
        # Verify thread configuration
        self.assertEqual(call_kwargs['daemon'], True)
        self.assertEqual(call_kwargs['args'], (self.meeting.id, self.user1.id))
        
        # Verify thread was started
        mock_thread.start.assert_called_once()

    @patch('home.views.threading.Thread')
    def test_view_returns_immediately(self, mock_thread_class):
        """Test that view returns immediately without waiting for thread"""
        mock_thread = Mock()
        mock_thread_class.return_value = mock_thread
        
        self.client.login(username='user1', password='TestPass123')
        
        start_time = time.time()
        response = self.client.post(
            reverse('generate_tasks_from_meeting', args=[self.meeting.id])
        )
        end_time = time.time()
        
        # Response should be nearly instant (< 1 second)
        self.assertLess(end_time - start_time, 1.0)
        
        # Should redirect
        self.assertEqual(response.status_code, 302)

    def test_view_requires_post(self):
        """Test that view requires POST method"""
        self.client.login(username='user1', password='TestPass123')
        
        response = self.client.get(
            reverse('generate_tasks_from_meeting', args=[self.meeting.id])
        )
        
        self.assertEqual(response.status_code, 403)

    def test_view_requires_authentication(self):
        """Test that view requires user to be logged in"""
        response = self.client.post(
            reverse('generate_tasks_from_meeting', args=[self.meeting.id])
        )
        
        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_view_requires_permission(self):
        """Test that view requires appropriate permissions"""
        other_user = User.objects.create_user(username='other', password='TestPass123')
        UserProfile.objects.create(user=other_user, display_name='Other User')
        
        self.client.login(username='other', password='TestPass123')
        
        response = self.client.post(
            reverse('generate_tasks_from_meeting', args=[self.meeting.id])
        )
        
        # Should redirect to dashboard with error
        self.assertEqual(response.status_code, 302)

    @patch('home.views.threading.Thread')
    def test_view_success_message(self, mock_thread_class):
        """Test that view shows appropriate success message"""
        mock_thread = Mock()
        mock_thread_class.return_value = mock_thread
        
        self.client.login(username='user1', password='TestPass123')
        
        response = self.client.post(
            reverse('generate_tasks_from_meeting', args=[self.meeting.id]),
            follow=True
        )
        
        # Check for success message
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertIn('Task generation started', str(messages[0]))

    @patch('home.views.threading.Thread')
    def test_view_redirects_to_workspace(self, mock_thread_class):
        """Test that view redirects to workspace detail page"""
        mock_thread = Mock()
        mock_thread_class.return_value = mock_thread
        
        self.client.login(username='user1', password='TestPass123')
        
        response = self.client.post(
            reverse('generate_tasks_from_meeting', args=[self.meeting.id])
        )
        
        # Should redirect to workspace detail
        self.assertRedirects(
            response,
            reverse('workspace_detail', args=[self.workspace.id]),
            fetch_redirect_response=False
        )

    @patch('home.views.threading.Thread')
    def test_multiple_concurrent_requests(self, mock_thread_class):
        """Test that multiple concurrent requests create separate threads"""
        mock_threads = [Mock(), Mock(), Mock()]
        mock_thread_class.side_effect = mock_threads
        
        self.client.login(username='user1', password='TestPass123')
        
        # Make multiple requests
        for _ in range(3):
            self.client.post(
                reverse('generate_tasks_from_meeting', args=[self.meeting.id])
            )
        
        # Verify 3 separate threads were created and started
        self.assertEqual(mock_thread_class.call_count, 3)
        for mock_thread in mock_threads:
            mock_thread.start.assert_called_once()


class ThreadingSafetyTestCase(TestCase):
    """Test thread safety of the task extraction system"""

    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='TestPass123')
        self.profile1 = UserProfile.objects.create(user=self.user1, display_name='User One')
        
        self.workspace = Workspace.objects.create(name='Test Team', created_by=self.user1)
        WorkspaceMembership.objects.create(user=self.user1, workspace=self.workspace, role='admin')
        
        self.meeting = Meeting.objects.create(
            title='Test Meeting',
            room_name='test-room-123',
            created_by=self.user1,
            workspace=self.workspace,
            status='ended'
        )

    @skipIf(
        'sqlite' in settings.DATABASES['default']['ENGINE'],
        "SQLite doesn't handle concurrent writes well in tests"
    )
    
    @patch('home.meeting_ai.get_client')
    def test_concurrent_task_extraction(self, mock_get_client):
        """Test that concurrent task extractions don't interfere with each other"""
        from home.meeting_ai import extract_tasks_from_meeting_threaded
        
        # Create two meetings with different transcripts
        meeting2 = Meeting.objects.create(
            title='Test Meeting 2',
            room_name='test-room-456',
            created_by=self.user1,
            workspace=self.workspace,
            status='ended'
        )
        
        MeetingTranscriptChunk.objects.create(
            meeting=self.meeting,
            speaker='User One',
            text='Task A'
        )
        
        MeetingTranscriptChunk.objects.create(
            meeting=meeting2,
            speaker='User One',
            text='Task B'
        )
        
        # Mock responses
        def create_response(task_title):
            mock_response = Mock()
            mock_response.content = [Mock(text=json.dumps({
                "tasks": [{"title": task_title, "assignee": "", "due_date": "", "priority": "", "notes": ""}]
            }))]
            return mock_response
        
        mock_client = Mock()
        mock_client.messages.create.side_effect = [
            create_response("Task from meeting 1"),
            create_response("Task from meeting 2")
        ]
        mock_get_client.return_value = mock_client
        
        # Run both in threads
        thread1 = threading.Thread(
            target=extract_tasks_from_meeting_threaded,
            args=(self.meeting.id, self.user1.id),
            daemon=True
        )
        thread2 = threading.Thread(
            target=extract_tasks_from_meeting_threaded,
            args=(meeting2.id, self.user1.id),
            daemon=True
        )
        
        thread1.start()
        thread2.start()
        
        thread1.join(timeout=5)
        thread2.join(timeout=5)
        
        # Wait for database writes
        time.sleep(0.2)
        
        # Both tasks should be created
        self.assertEqual(Task.objects.count(), 2)