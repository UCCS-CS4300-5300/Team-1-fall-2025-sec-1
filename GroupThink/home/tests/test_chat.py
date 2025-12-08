"""Comprehensive test cases for team chat functionality."""
import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase

from home.models import (
    ChatAttachment,
    ChatMessage,
    UserProfile,
    Workspace,
    WorkspaceMembership,
)

User = get_user_model()


class ChatMessageModelTest(TestCase):
    """Test ChatMessage model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.workspace = Workspace.objects.create(
            name='Test Workspace',
            created_by=self.user
        )
        WorkspaceMembership.objects.create(
            user=self.user,
            workspace=self.workspace,
            role='admin'
        )

    def test_create_chat_message(self):
        """Test creating a chat message"""
        message = ChatMessage.objects.create(
            workspace=self.workspace,
            sender=self.user,
            message='Hello team!'
        )
        self.assertEqual(message.message, 'Hello team!')
        self.assertEqual(message.sender, self.user)
        self.assertEqual(message.workspace, self.workspace)

    def test_chat_message_ordering(self):
        """Test that messages are ordered by creation time"""
        msg1 = ChatMessage.objects.create(
            workspace=self.workspace,
            sender=self.user,
            message='First message'
        )
        msg2 = ChatMessage.objects.create(
            workspace=self.workspace,
            sender=self.user,
            message='Second message'
        )

        messages = list(ChatMessage.objects.all())
        self.assertEqual(messages[0], msg1)
        self.assertEqual(messages[1], msg2)

    def test_chat_message_str(self):
        """Test string representation of chat message"""
        message = ChatMessage.objects.create(
            workspace=self.workspace,
            sender=self.user,
            message='Test message for string representation'
        )
        expected = f"{self.user.username} in {self.workspace.name}: Test message for string representation"
        self.assertEqual(str(message), expected)


class ChatAttachmentModelTest(TestCase):
    """Test ChatAttachment model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.workspace = Workspace.objects.create(
            name='Test Workspace',
            created_by=self.user
        )
        self.message = ChatMessage.objects.create(
            workspace=self.workspace,
            sender=self.user,
            message='Message with attachment'
        )

    def test_file_size_display_bytes(self):
        """Test file size display for bytes"""
        attachment = ChatAttachment.objects.create(
            chat_message=self.message,
            file='test.txt',
            file_name='test.txt',
            file_size=500
        )
        self.assertEqual(attachment.get_file_size_display(), '500.0 B')

    def test_file_size_display_kilobytes(self):
        """Test file size display for kilobytes"""
        attachment = ChatAttachment.objects.create(
            chat_message=self.message,
            file='test.txt',
            file_name='test.txt',
            file_size=2048
        )
        self.assertEqual(attachment.get_file_size_display(), '2.0 KB')

    def test_file_size_display_megabytes(self):
        """Test file size display for megabytes"""
        attachment = ChatAttachment.objects.create(
            chat_message=self.message,
            file='test.txt',
            file_name='test.txt',
            file_size=5 * 1024 * 1024
        )
        self.assertEqual(attachment.get_file_size_display(), '5.0 MB')


class SendChatMessageViewTest(TestCase):
    """Test send_chat_message view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        UserProfile.objects.create(user=self.user, display_name='Test User')

        self.other_user = User.objects.create_user(username='otheruser', password='testpass123')
        UserProfile.objects.create(user=self.other_user, display_name='Other User')

        self.workspace = Workspace.objects.create(
            name='Test Workspace',
            created_by=self.user
        )
        WorkspaceMembership.objects.create(
            user=self.user,
            workspace=self.workspace,
            role='admin'
        )

    def test_send_message_success(self):
        """Test sending a message successfully"""
        self.client.login(username='testuser', password='testpass123')

        response = self.client.post(
            f'/workspace/{self.workspace.id}/chat/send/',
            {'message': 'Hello world!'}
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['message'], 'Hello world!')
        self.assertEqual(data['sender'], 'Test User')

        # Verify message was saved
        self.assertEqual(ChatMessage.objects.count(), 1)
        message = ChatMessage.objects.first()
        self.assertEqual(message.message, 'Hello world!')

    def test_send_message_requires_login(self):
        """Test that sending a message requires authentication"""
        response = self.client.post(
            f'/workspace/{self.workspace.id}/chat/send/',
            {'message': 'Hello!'}
        )
        # Should redirect to login
        self.assertEqual(response.status_code, 302)

    def test_send_message_requires_membership(self):
        """Test that only workspace members can send messages"""
        self.client.login(username='otheruser', password='testpass123')

        response = self.client.post(
            f'/workspace/{self.workspace.id}/chat/send/',
            {'message': 'Hello!'}
        )

        self.assertEqual(response.status_code, 403)
        data = json.loads(response.content)
        self.assertIn('error', data)

    def test_send_empty_message_fails(self):
        """Test that sending an empty message fails"""
        self.client.login(username='testuser', password='testpass123')

        response = self.client.post(
            f'/workspace/{self.workspace.id}/chat/send/',
            {'message': ''}
        )

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn('error', data)

    def test_send_message_with_file(self):
        """Test sending a message with a file attachment"""
        self.client.login(username='testuser', password='testpass123')

        # Create a test file
        test_file = SimpleUploadedFile(
            'test.txt',
            b'Test file content',
            content_type='text/plain'
        )

        response = self.client.post(
            f'/workspace/{self.workspace.id}/chat/send/',
            {
                'message': 'Check out this file!',
                'file': test_file
            }
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])

        # Verify attachment was saved
        self.assertEqual(ChatAttachment.objects.count(), 1)
        attachment = ChatAttachment.objects.first()
        self.assertEqual(attachment.file_name, 'test.txt')

    def test_send_file_only(self):
        """Test sending a file without a message"""
        self.client.login(username='testuser', password='testpass123')

        test_file = SimpleUploadedFile(
            'document.pdf',
            b'PDF content here',
            content_type='application/pdf'
        )

        response = self.client.post(
            f'/workspace/{self.workspace.id}/chat/send/',
            {'file': test_file}
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])

        # Should create a default message
        message = ChatMessage.objects.first()
        self.assertIn('document.pdf', message.message)

    def test_file_size_limit(self):
        """Test that files over 10MB are rejected"""
        self.client.login(username='testuser', password='testpass123')

        # Create a file larger than 10MB
        large_file = SimpleUploadedFile(
            'large.bin',
            b'x' * (11 * 1024 * 1024),  # 11MB
            content_type='application/octet-stream'
        )

        response = self.client.post(
            f'/workspace/{self.workspace.id}/chat/send/',
            {'file': large_file}
        )

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn('error', data)
        self.assertIn('10MB', data['error'])

    def test_get_request_fails(self):
        """Test that GET requests are rejected"""
        self.client.login(username='testuser', password='testpass123')

        response = self.client.get(f'/workspace/{self.workspace.id}/chat/send/')

        self.assertEqual(response.status_code, 400)


class GetChatMessagesViewTest(TestCase):
    """Test get_chat_messages view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        UserProfile.objects.create(user=self.user, display_name='Test User')

        self.workspace = Workspace.objects.create(
            name='Test Workspace',
            created_by=self.user
        )
        WorkspaceMembership.objects.create(
            user=self.user,
            workspace=self.workspace,
            role='admin'
        )

    def test_get_messages_success(self):
        """Test retrieving messages successfully"""
        # Create some messages
        msg1 = ChatMessage.objects.create(
            workspace=self.workspace,
            sender=self.user,
            message='First message'
        )
        msg2 = ChatMessage.objects.create(
            workspace=self.workspace,
            sender=self.user,
            message='Second message'
        )

        self.client.login(username='testuser', password='testpass123')

        response = self.client.get(f'/workspace/{self.workspace.id}/chat/messages/')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(len(data['messages']), 2)
        self.assertEqual(data['messages'][0]['message'], 'First message')
        self.assertEqual(data['messages'][1]['message'], 'Second message')

    def test_get_messages_requires_login(self):
        """Test that getting messages requires authentication"""
        response = self.client.get(f'/workspace/{self.workspace.id}/chat/messages/')

        # Should redirect to login
        self.assertEqual(response.status_code, 302)

    def test_get_messages_requires_membership(self):
        """Test that only workspace members can get messages"""
        other_user = User.objects.create_user(username='otheruser', password='testpass123')
        UserProfile.objects.create(user=other_user, display_name='Other User')
        self.client.login(username='otheruser', password='testpass123')

        response = self.client.get(f'/workspace/{self.workspace.id}/chat/messages/')

        self.assertEqual(response.status_code, 403)

    def test_get_messages_with_since_id(self):
        """Test polling for new messages using since_id"""
        # Create initial messages
        msg1 = ChatMessage.objects.create(
            workspace=self.workspace,
            sender=self.user,
            message='Old message'
        )
        msg2 = ChatMessage.objects.create(
            workspace=self.workspace,
            sender=self.user,
            message='New message'
        )

        self.client.login(username='testuser', password='testpass123')

        # Get only messages after msg1
        response = self.client.get(
            f'/workspace/{self.workspace.id}/chat/messages/?since_id={msg1.id}'
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(len(data['messages']), 1)
        self.assertEqual(data['messages'][0]['message'], 'New message')

    def test_get_messages_with_attachments(self):
        """Test that attachments are included in message data"""
        message = ChatMessage.objects.create(
            workspace=self.workspace,
            sender=self.user,
            message='Message with file'
        )

        # Create attachment
        attachment = ChatAttachment.objects.create(
            chat_message=message,
            file='test.txt',
            file_name='test.txt',
            file_size=1024
        )

        self.client.login(username='testuser', password='testpass123')

        response = self.client.get(f'/workspace/{self.workspace.id}/chat/messages/')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(len(data['messages']), 1)
        self.assertEqual(len(data['messages'][0]['attachments']), 1)
        self.assertEqual(data['messages'][0]['attachments'][0]['file_name'], 'test.txt')

    def test_message_ownership_flag(self):
        """Test that is_own_message flag is set correctly"""
        other_user = User.objects.create_user(username='otheruser', password='testpass123')
        UserProfile.objects.create(user=other_user, display_name='Other User')

        WorkspaceMembership.objects.create(
            user=other_user,
            workspace=self.workspace,
            role='member'
        )

        # Create messages from both users
        my_message = ChatMessage.objects.create(
            workspace=self.workspace,
            sender=self.user,
            message='My message'
        )
        their_message = ChatMessage.objects.create(
            workspace=self.workspace,
            sender=other_user,
            message='Their message'
        )

        self.client.login(username='testuser', password='testpass123')

        response = self.client.get(f'/workspace/{self.workspace.id}/chat/messages/')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(len(data['messages']), 2)

        # Check ownership flags
        self.assertTrue(data['messages'][0]['is_own_message'])  # My message
        self.assertFalse(data['messages'][1]['is_own_message'])  # Their message


class ChatIntegrationTest(TestCase):
    """Integration tests for chat functionality"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user1 = User.objects.create_user(username='user1', password='testpass123')
        UserProfile.objects.create(user=self.user1, display_name='User One')

        self.user2 = User.objects.create_user(username='user2', password='testpass123')
        UserProfile.objects.create(user=self.user2, display_name='User Two')

        self.workspace = Workspace.objects.create(
            name='Team Workspace',
            created_by=self.user1
        )

        WorkspaceMembership.objects.create(
            user=self.user1,
            workspace=self.workspace,
            role='admin'
        )
        WorkspaceMembership.objects.create(
            user=self.user2,
            workspace=self.workspace,
            role='member'
        )

    def test_chat_conversation_flow(self):
        """Test a complete chat conversation between two users"""
        # User 1 sends a message
        self.client.login(username='user1', password='testpass123')
        response = self.client.post(
            f'/workspace/{self.workspace.id}/chat/send/',
            {'message': 'Hello team!'}
        )
        self.assertEqual(response.status_code, 200)

        # User 2 receives the message
        self.client.login(username='user2', password='testpass123')
        response = self.client.get(f'/workspace/{self.workspace.id}/chat/messages/')
        data = json.loads(response.content)
        self.assertEqual(len(data['messages']), 1)
        self.assertEqual(data['messages'][0]['sender'], 'User One')

        # User 2 replies
        response = self.client.post(
            f'/workspace/{self.workspace.id}/chat/send/',
            {'message': 'Hi there!'}
        )
        self.assertEqual(response.status_code, 200)

        # User 1 sees both messages
        self.client.login(username='user1', password='testpass123')
        response = self.client.get(f'/workspace/{self.workspace.id}/chat/messages/')
        data = json.loads(response.content)
        self.assertEqual(len(data['messages']), 2)

    def test_chat_history_persistence(self):
        """Test that chat history persists across sessions"""
        # Send messages
        self.client.login(username='user1', password='testpass123')
        self.client.post(
            f'/workspace/{self.workspace.id}/chat/send/',
            {'message': 'Message 1'}
        )
        self.client.post(
            f'/workspace/{self.workspace.id}/chat/send/',
            {'message': 'Message 2'}
        )

        # Logout and login as different user
        self.client.logout()
        self.client.login(username='user2', password='testpass123')

        # Should still see all messages
        response = self.client.get(f'/workspace/{self.workspace.id}/chat/messages/')
        data = json.loads(response.content)
        self.assertEqual(len(data['messages']), 2)

    def test_multiple_workspaces_isolation(self):
        """Test that chat messages are isolated per workspace"""
        # Create second workspace
        workspace2 = Workspace.objects.create(
            name='Other Workspace',
            created_by=self.user1
        )
        WorkspaceMembership.objects.create(
            user=self.user1,
            workspace=workspace2,
            role='admin'
        )

        # Send message in first workspace
        self.client.login(username='user1', password='testpass123')
        self.client.post(
            f'/workspace/{self.workspace.id}/chat/send/',
            {'message': 'Workspace 1 message'}
        )

        # Send message in second workspace
        self.client.post(
            f'/workspace/{workspace2.id}/chat/send/',
            {'message': 'Workspace 2 message'}
        )

        # Check workspace 1 only has its message
        response = self.client.get(f'/workspace/{self.workspace.id}/chat/messages/')
        data = json.loads(response.content)
        self.assertEqual(len(data['messages']), 1)
        self.assertEqual(data['messages'][0]['message'], 'Workspace 1 message')

        # Check workspace 2 only has its message
        response = self.client.get(f'/workspace/{workspace2.id}/chat/messages/')
        data = json.loads(response.content)
        self.assertEqual(len(data['messages']), 1)
        self.assertEqual(data['messages'][0]['message'], 'Workspace 2 message')
