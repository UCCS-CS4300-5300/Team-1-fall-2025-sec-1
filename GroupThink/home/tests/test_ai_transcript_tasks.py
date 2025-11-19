from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from home.models import UserProfile, Workspace, WorkspaceMembership, Meeting, Task, MeetingTranscriptChunk
from home.meeting_ai import extract_tasks_from_meeting, _assemble_transcript_text, get_client
from django.utils import timezone
from unittest.mock import patch, Mock
import json
from datetime import date, timedelta


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
        
        .-*-* 568        client1 = get_client()
        client2 = get_client()
        
        # Should only create once
        self.assertEqual(mock_anthropic.call_count, 1)
        self.assertEqual(client1, client2)