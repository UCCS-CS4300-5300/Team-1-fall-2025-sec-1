"""Comprehensive tests for GroupThink application features."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from home.forms import JoinWorkspaceForm, LoginForm, SignUpForm, TaskForm, WorkspaceForm
from home.models import Meeting, Task, UserProfile, Workspace, WorkspaceMembership

User = get_user_model()


class AuthenticationTestCase(TestCase):
    """Test user authentication features"""

    def setUp(self):
        self.client = Client()

    def test_signup_page_loads(self):
        """Test signup page renders correctly"""
        response = self.client.get(reverse('signup'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home/signup.html')

    def test_signup_creates_user_and_profile(self):
        """Test successful user registration with email verification"""
        from home.models import PendingUser

        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'display_name': 'Test User',
            'password1': 'TestPass123',
            'password2': 'TestPass123',
        }
        response = self.client.post(reverse('signup'), data)

        # Should show verify email page, not redirect
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home/verify_email_sent.html')

        # Check PendingUser created (not User yet)
        pending_user = PendingUser.objects.get(username='testuser')
        self.assertEqual(pending_user.email, 'test@example.com')
        self.assertEqual(pending_user.display_name, 'Test User')
        self.assertTrue(len(pending_user.verification_token) > 0)

        # Check User NOT created yet (requires email verification)
        self.assertEqual(User.objects.filter(username='testuser').count(), 0)

    def test_signup_password_validation(self):
        """Test password strength requirements"""
        # Too short
        form = SignUpForm(data={
            'username': 'test',
            'email': 'test@example.com',
            'display_name': 'Test',
            'password1': 'short',
            'password2': 'short',
        })
        self.assertFalse(form.is_valid())

        # No uppercase
        form = SignUpForm(data={
            'username': 'test',
            'email': 'test@example.com',
            'display_name': 'Test',
            'password1': 'testpass123',
            'password2': 'testpass123',
        })
        self.assertFalse(form.is_valid())

        # Valid password
        form = SignUpForm(data={
            'username': 'test',
            'email': 'test@example.com',
            'display_name': 'Test',
            'password1': 'TestPass123',
            'password2': 'TestPass123',
        })
        self.assertTrue(form.is_valid())

    def test_duplicate_username_rejected(self):
        """Test that duplicate usernames are rejected"""
        # Create first user
        User.objects.create_user(username='testuser', password='TestPass123')

        # Try to create second user with same username
        form = SignUpForm(data={
            'username': 'testuser',
            'email': 'different@example.com',
            'display_name': 'Different User',
            'password1': 'TestPass123',
            'password2': 'TestPass123',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('username', form.errors)

    def test_duplicate_email_rejected(self):
        """Test that duplicate emails are rejected"""
        # Create first user
        user = User.objects.create_user(username='user1', email='test@example.com')
        UserProfile.objects.create(user=user, display_name='User 1')

        # Try to create second user with same email
        form = SignUpForm(data={
            'username': 'user2',
            'email': 'test@example.com',
            'display_name': 'User 2',
            'password1': 'TestPass123',
            'password2': 'TestPass123',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_login_with_username(self):
        """Test login with username"""
        # Create user
        user = User.objects.create_user(username='testuser', password='TestPass123')
        UserProfile.objects.create(user=user, display_name='Test User')

        # Login
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'TestPass123',
        })

        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_login_with_email(self):
        """Test login with email address"""
        # Create user
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='TestPass123'
        )
        UserProfile.objects.create(user=user, display_name='Test User')

        # Login with email
        response = self.client.post(reverse('login'), {
            'username': 'test@example.com',
            'password': 'TestPass123',
        })

        self.assertRedirects(response, reverse('dashboard'))

    def test_login_invalid_credentials(self):
        """Test login with wrong password"""
        user = User.objects.create_user(username='testuser', password='TestPass123')
        UserProfile.objects.create(user=user, display_name='Test User')

        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'WrongPassword',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_logout(self):
        """Test logout functionality"""
        user = User.objects.create_user(username='testuser', password='TestPass123')
        UserProfile.objects.create(user=user, display_name='Test User')
        self.client.login(username='testuser', password='TestPass123')

        response = self.client.get(reverse('logout'))
        self.assertRedirects(response, reverse('index'))

    def test_homepage_redirects_authenticated_user(self):
        """Test that logged-in users are redirected to dashboard from homepage"""
        user = User.objects.create_user(username='testuser', password='TestPass123')
        UserProfile.objects.create(user=user, display_name='Test User')
        self.client.login(username='testuser', password='TestPass123')

        response = self.client.get(reverse('index'))
        self.assertRedirects(response, reverse('dashboard'))


class WorkspaceTeamTestCase(TestCase):
    """Test team/workspace management features"""

    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(username='user1', password='TestPass123')
        self.profile1 = UserProfile.objects.create(user=self.user1, display_name='User One')
        self.user2 = User.objects.create_user(username='user2', password='TestPass123')
        self.profile2 = UserProfile.objects.create(user=self.user2, display_name='User Two')

    def test_create_workspace(self):
        """Test workspace creation"""
        self.client.login(username='user1', password='TestPass123')

        response = self.client.post(reverse('create_workspace'), {
            'name': 'Test Team',
        })

        # Check workspace created
        workspace = Workspace.objects.get(name='Test Team')
        self.assertEqual(workspace.created_by, self.user1)
        self.assertTrue(len(workspace.invite_code) == 8)

        # Check creator is admin
        membership = WorkspaceMembership.objects.get(user=self.user1, workspace=workspace)
        self.assertEqual(membership.role, 'admin')

    def test_join_workspace_with_code(self):
        """Test joining a workspace with invite code"""
        # Create workspace
        workspace = Workspace.objects.create(name='Test Team', created_by=self.user1)
        WorkspaceMembership.objects.create(user=self.user1, workspace=workspace, role='admin')

        # User 2 joins
        self.client.login(username='user2', password='TestPass123')
        response = self.client.post(reverse('join_workspace'), {
            'invite_code': workspace.invite_code,
        })

        # Check membership created
        membership = WorkspaceMembership.objects.filter(user=self.user2, workspace=workspace).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.role, 'member')

    def test_join_workspace_invalid_code(self):
        """Test joining with invalid invite code"""
        self.client.login(username='user1', password='TestPass123')

        response = self.client.post(reverse('join_workspace'), {
            'invite_code': 'INVALID1',
        })

        self.assertEqual(response.status_code, 200)
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any('Invalid invite code' in m for m in messages))

    def test_join_workspace_already_member(self):
        """Test joining a workspace user is already in"""
        workspace = Workspace.objects.create(name='Test Team', created_by=self.user1)
        WorkspaceMembership.objects.create(user=self.user1, workspace=workspace, role='admin')

        self.client.login(username='user1', password='TestPass123')
        response = self.client.post(reverse('join_workspace'), {
            'invite_code': workspace.invite_code,
        })

        # Check warning message
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any('already a member' in m for m in messages))

    def test_workspace_code_visibility_toggle(self):
        """Test admin can toggle code visibility"""
        workspace = Workspace.objects.create(name='Test Team', created_by=self.user1)
        WorkspaceMembership.objects.create(user=self.user1, workspace=workspace, role='admin')

        self.client.login(username='user1', password='TestPass123')

        # Toggle on
        response = self.client.post(reverse('toggle_code_visibility', args=[workspace.id]))
        workspace.refresh_from_db()
        self.assertTrue(workspace.code_visible_to_members)

        # Toggle off
        response = self.client.post(reverse('toggle_code_visibility', args=[workspace.id]))
        workspace.refresh_from_db()
        self.assertFalse(workspace.code_visible_to_members)

    def test_non_admin_cannot_toggle_code_visibility(self):
        """Test that non-admin members cannot toggle code visibility"""
        workspace = Workspace.objects.create(name='Test Team', created_by=self.user1)
        WorkspaceMembership.objects.create(user=self.user1, workspace=workspace, role='admin')
        WorkspaceMembership.objects.create(user=self.user2, workspace=workspace, role='member')

        # User 2 (member) tries to toggle
        self.client.login(username='user2', password='TestPass123')
        response = self.client.post(reverse('toggle_code_visibility', args=[workspace.id]))

        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any('permission' in m.lower() for m in messages))

    def test_admin_can_remove_member(self):
        """Test admin can remove team members"""
        workspace = Workspace.objects.create(name='Test Team', created_by=self.user1)
        WorkspaceMembership.objects.create(user=self.user1, workspace=workspace, role='admin')
        WorkspaceMembership.objects.create(user=self.user2, workspace=workspace, role='member')

        self.client.login(username='user1', password='TestPass123')
        response = self.client.post(reverse('remove_member', args=[workspace.id, self.user2.id]))

        # Check user2 removed
        membership = WorkspaceMembership.objects.filter(user=self.user2, workspace=workspace).first()
        self.assertIsNone(membership)

    def test_cannot_remove_workspace_creator(self):
        """Test that workspace creator cannot be removed"""
        workspace = Workspace.objects.create(name='Test Team', created_by=self.user1)
        WorkspaceMembership.objects.create(user=self.user1, workspace=workspace, role='admin')

        self.client.login(username='user1', password='TestPass123')
        response = self.client.post(reverse('remove_member', args=[workspace.id, self.user1.id]))

        # Check creator still member
        membership = WorkspaceMembership.objects.filter(user=self.user1, workspace=workspace).first()
        self.assertIsNotNone(membership)

    def test_non_admin_cannot_remove_member(self):
        """Test that regular members cannot remove other members"""
        workspace = Workspace.objects.create(name='Test Team', created_by=self.user1)
        WorkspaceMembership.objects.create(user=self.user1, workspace=workspace, role='admin')
        WorkspaceMembership.objects.create(user=self.user2, workspace=workspace, role='member')

        # User 2 tries to remove user1
        self.client.login(username='user2', password='TestPass123')
        response = self.client.post(reverse('remove_member', args=[workspace.id, self.user1.id]))

        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any('permission' in m.lower() for m in messages))

class MeetingTestCase(TestCase):
    """Test meeting management features"""

    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(username='user1', password='TestPass123')
        self.profile1 = UserProfile.objects.create(user=self.user1, display_name='User One')
        self.user2 = User.objects.create_user(username='user2', password='TestPass123')
        self.profile2 = UserProfile.objects.create(user=self.user2, display_name='User Two')

        self.workspace = Workspace.objects.create(name='Test Team', created_by=self.user1)
        WorkspaceMembership.objects.create(user=self.user1, workspace=self.workspace, role='admin')

    def test_create_meeting_in_workspace(self):
        """Test creating a meeting within a workspace"""
        self.client.login(username='user1', password='TestPass123')

        response = self.client.post(reverse('create_meeting'), {
            'title': 'Test Meeting',
            'workspace': self.workspace.id,
        })

        # Check meeting created
        meeting = Meeting.objects.get(title='Test Meeting')
        self.assertEqual(meeting.workspace, self.workspace)
        self.assertEqual(meeting.created_by, self.user1)
        self.assertEqual(meeting.status, 'not_started')

    def test_create_personal_meeting(self):
        """Test creating a personal meeting without workspace"""
        self.client.login(username='user1', password='TestPass123')

        response = self.client.post(reverse('create_meeting'), {
            'title': 'Personal Meeting',
        })

        meeting = Meeting.objects.get(title='Personal Meeting')
        self.assertIsNone(meeting.workspace)
        self.assertEqual(meeting.created_by, self.user1)

    def test_meeting_access_control(self):
        """Test that only workspace members can access workspace meetings"""
        # Create meeting in workspace
        meeting = Meeting.objects.create(
            title='Team Meeting',
            room_name='test-room-123',
            created_by=self.user1,
            workspace=self.workspace
        )

        # User 2 (not a member) tries to access
        self.client.login(username='user2', password='TestPass123')
        response = self.client.get(reverse('join_meeting', args=[meeting.room_name]))

        self.assertRedirects(response, reverse('dashboard'))

    def test_delete_meeting_creator(self):
        """Test meeting creator can delete their meeting"""
        meeting = Meeting.objects.create(
            title='Test Meeting',
            room_name='test-room-123',
            created_by=self.user1,
            workspace=self.workspace
        )

        self.client.login(username='user1', password='TestPass123')
        response = self.client.post(reverse('delete_meeting', args=[meeting.id]))

        # Check meeting deleted
        self.assertFalse(Meeting.objects.filter(id=meeting.id).exists())

    def test_delete_meeting_workspace_admin(self):
        """Test workspace admin can delete any meeting in their workspace"""
        # User 2 creates a meeting
        WorkspaceMembership.objects.create(user=self.user2, workspace=self.workspace, role='member')
        meeting = Meeting.objects.create(
            title='Test Meeting',
            room_name='test-room-123',
            created_by=self.user2,
            workspace=self.workspace
        )

        # User 1 (admin) deletes it
        self.client.login(username='user1', password='TestPass123')
        response = self.client.post(reverse('delete_meeting', args=[meeting.id]))

        self.assertFalse(Meeting.objects.filter(id=meeting.id).exists())

    def test_non_creator_cannot_delete_meeting(self):
        """Test that non-creators/non-admins cannot delete meetings"""
        meeting = Meeting.objects.create(
            title='Test Meeting',
            room_name='test-room-123',
            created_by=self.user1
        )

        # User 2 tries to delete
        self.client.login(username='user2', password='TestPass123')
        response = self.client.post(reverse('delete_meeting', args=[meeting.id]))

        # Meeting still exists
        self.assertTrue(Meeting.objects.filter(id=meeting.id).exists())

    def test_update_meeting_status_to_live(self):
        """Test updating meeting status to live"""
        meeting = Meeting.objects.create(
            title='Test Meeting',
            room_name='test-room-123',
            created_by=self.user1,
            workspace=self.workspace
        )

        self.client.login(username='user1', password='TestPass123')
        response = self.client.post(reverse('update_meeting_status', args=[meeting.id]), {
            'status': 'live',
        })

        meeting.refresh_from_db()
        self.assertEqual(meeting.status, 'live')
        self.assertIsNotNone(meeting.started_at)

    def test_update_meeting_status_to_ended(self):
        """Test updating meeting status to ended"""
        meeting = Meeting.objects.create(
            title='Test Meeting',
            room_name='test-room-123',
            created_by=self.user1,
            workspace=self.workspace,
            status='live',
            started_at=timezone.now()
        )

        self.client.login(username='user1', password='TestPass123')
        response = self.client.post(reverse('update_meeting_status', args=[meeting.id]), {
            'status': 'ended',
        })

        meeting.refresh_from_db()
        self.assertEqual(meeting.status, 'ended')
        self.assertIsNotNone(meeting.ended_at)

    def test_meeting_status_choices(self):
        """Test that meeting has correct status choices"""
        self.assertEqual(Meeting.STATUS_CHOICES, [
            ('not_started', 'Not Started'),
            ('live', 'Live'),
            ('ended', 'Ended'),
        ])

    def test_meeting_recording_url_field(self):
        """Test meeting can store recording URL"""
        meeting = Meeting.objects.create(
            title='Test Meeting',
            room_name='test-room-123',
            created_by=self.user1,
            status='ended',
            recording_url='https://example.com/recording.mp4'
        )

        self.assertEqual(meeting.recording_url, 'https://example.com/recording.mp4')


class DashboardTestCase(TestCase):
    """Test dashboard functionality"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='TestPass123')
        self.profile = UserProfile.objects.create(user=self.user, display_name='Test User')

    def test_dashboard_requires_login(self):
        """Test dashboard redirects anonymous users"""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_shows_user_workspaces(self):
        """Test dashboard displays user's workspaces"""
        workspace1 = Workspace.objects.create(name='Team 1', created_by=self.user)
        workspace2 = Workspace.objects.create(name='Team 2', created_by=self.user)
        WorkspaceMembership.objects.create(user=self.user, workspace=workspace1, role='admin')
        WorkspaceMembership.objects.create(user=self.user, workspace=workspace2, role='admin')

        self.client.login(username='testuser', password='TestPass123')
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('workspaces', response.context)
        self.assertEqual(len(response.context['workspaces']), 2)


class FormValidationTestCase(TestCase):
    """Test form validations"""

    def test_workspace_form_validation(self):
        """Test workspace form accepts valid data"""
        form = WorkspaceForm(data={'name': 'Test Team'})
        self.assertTrue(form.is_valid())

    def test_join_workspace_form_uppercases_code(self):
        """Test join workspace form uppercases invite codes"""
        form = JoinWorkspaceForm(data={'invite_code': 'abc123'})
        if form.is_valid():
            self.assertEqual(form.cleaned_data['invite_code'], 'ABC123')

    def test_username_format_validation(self):
        """Test username only allows alphanumeric and underscores"""
        # Invalid characters
        form = SignUpForm(data={
            'username': 'test@user',
            'email': 'test@example.com',
            'display_name': 'Test',
            'password1': 'TestPass123',
            'password2': 'TestPass123',
        })
        self.assertFalse(form.is_valid())

        # Valid username
        form = SignUpForm(data={
            'username': 'test_user123',
            'email': 'test@example.com',
            'display_name': 'Test',
            'password1': 'TestPass123',
            'password2': 'TestPass123',
        })
        self.assertTrue(form.is_valid())


class ModelTestCase(TestCase):
    """Test model methods and properties"""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser')
        self.profile = UserProfile.objects.create(user=self.user, display_name='Test User')

    def test_userprofile_str(self):
        """Test UserProfile string representation"""
        self.assertEqual(str(self.profile), 'testuser - Test User')

    def test_workspace_str(self):
        """Test Workspace string representation"""
        workspace = Workspace.objects.create(name='Test Team', created_by=self.user)
        self.assertEqual(str(workspace), 'Test Team')

    def test_workspace_auto_generates_invite_code(self):
        """Test that workspace automatically generates invite code"""
        workspace = Workspace.objects.create(name='Test Team', created_by=self.user)
        self.assertIsNotNone(workspace.invite_code)
        self.assertEqual(len(workspace.invite_code), 8)

    def test_workspacemembership_str(self):
        """Test WorkspaceMembership string representation"""
        workspace = Workspace.objects.create(name='Test Team', created_by=self.user)
        membership = WorkspaceMembership.objects.create(
            user=self.user,
            workspace=workspace,
            role='admin'
        )
        self.assertEqual(str(membership), 'testuser in Test Team (admin)')

    def test_meeting_str(self):
        """Test Meeting string representation"""
        meeting = Meeting.objects.create(
            title='Test Meeting',
            created_by=self.user,
            status='live'
        )
        self.assertEqual(str(meeting), 'Test Meeting - Live')

    def test_meeting_get_status_display(self):
        """Test meeting status display"""
        meeting = Meeting.objects.create(
            title='Test Meeting',
            created_by=self.user,
            status='not_started'
        )
        self.assertEqual(meeting.get_status_display(), 'Not Started')


class TaskManagementTestCase(TestCase):
    """Test task management features"""

    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(username='user1', password='TestPass123')
        self.profile1 = UserProfile.objects.create(user=self.user1, display_name='User One')
        self.user2 = User.objects.create_user(username='user2', password='TestPass123')
        self.profile2 = UserProfile.objects.create(user=self.user2, display_name='User Two')

        self.workspace = Workspace.objects.create(name='Test Team', created_by=self.user1)
        WorkspaceMembership.objects.create(user=self.user1, workspace=self.workspace, role='admin')
        WorkspaceMembership.objects.create(user=self.user2, workspace=self.workspace, role='member')

    def test_create_team_task(self):
        """Test creating a task in a team"""
        self.client.login(username='user1', password='TestPass123')

        response = self.client.post(reverse('create_task', args=[self.workspace.id]), {
            'title': 'Test Task',
            'description': 'This is a test task',
            'assigned_to': self.user2.id,
            'is_personal': False,
        })

        # Check task created
        task = Task.objects.get(title='Test Task')
        self.assertEqual(task.workspace, self.workspace)
        self.assertEqual(task.assigned_to, self.user2)
        self.assertEqual(task.created_by, self.user1)
        self.assertEqual(task.status, 'todo')
        self.assertFalse(task.is_personal)

    def test_create_personal_task(self):
        """Test creating a personal task"""
        self.client.login(username='user1', password='TestPass123')

        response = self.client.post(reverse('create_task', args=[self.workspace.id]), {
            'title': 'Personal Task',
            'description': 'My personal task',
            'assigned_to': self.user1.id,
            'is_personal': True,
        })

        task = Task.objects.get(title='Personal Task')
        self.assertIsNone(task.workspace)
        self.assertTrue(task.is_personal)

    def test_update_task_status_to_in_progress(self):
        """Test updating task status to in progress"""
        task = Task.objects.create(
            title='Test Task',
            workspace=self.workspace,
            assigned_to=self.user2,
            created_by=self.user1,
            status='todo'
        )

        self.client.login(username='user2', password='TestPass123')
        response = self.client.post(reverse('update_task_status', args=[task.id]), {
            'status': 'in_progress',
        })

        task.refresh_from_db()
        self.assertEqual(task.status, 'in_progress')

    def test_update_task_status_to_done(self):
        """Test updating task status to done"""
        task = Task.objects.create(
            title='Test Task',
            workspace=self.workspace,
            assigned_to=self.user2,
            created_by=self.user1,
            status='in_progress'
        )

        self.client.login(username='user2', password='TestPass123')
        response = self.client.post(reverse('update_task_status', args=[task.id]), {
            'status': 'done',
        })

        task.refresh_from_db()
        self.assertEqual(task.status, 'done')
        self.assertIsNotNone(task.completed_at)

    def test_task_mark_complete_method(self):
        """Test task mark_complete method"""
        task = Task.objects.create(
            title='Test Task',
            workspace=self.workspace,
            assigned_to=self.user2,
            created_by=self.user1,
            status='in_progress'
        )

        task.mark_complete()
        self.assertEqual(task.status, 'done')
        self.assertIsNotNone(task.completed_at)

    def test_assigned_user_can_update_task(self):
        """Test that assigned user can update task status"""
        task = Task.objects.create(
            title='Test Task',
            workspace=self.workspace,
            assigned_to=self.user2,
            created_by=self.user1
        )

        self.client.login(username='user2', password='TestPass123')
        response = self.client.post(reverse('update_task_status', args=[task.id]), {
            'status': 'in_progress',
        })

        task.refresh_from_db()
        self.assertEqual(task.status, 'in_progress')

    def test_workspace_admin_can_update_task(self):
        """Test that workspace admin can update any team task"""
        task = Task.objects.create(
            title='Test Task',
            workspace=self.workspace,
            assigned_to=self.user2,
            created_by=self.user2
        )

        self.client.login(username='user1', password='TestPass123')
        response = self.client.post(reverse('update_task_status', args=[task.id]), {
            'status': 'done',
        })

        task.refresh_from_db()
        self.assertEqual(task.status, 'done')

    def test_unrelated_user_cannot_update_task(self):
        """Test that unrelated users cannot update tasks"""
        user3 = User.objects.create_user(username='user3', password='TestPass123')
        UserProfile.objects.create(user=user3, display_name='User Three')

        task = Task.objects.create(
            title='Test Task',
            workspace=self.workspace,
            assigned_to=self.user2,
            created_by=self.user1
        )

        self.client.login(username='user3', password='TestPass123')
        response = self.client.post(reverse('update_task_status', args=[task.id]), {
            'status': 'done',
        })

        task.refresh_from_db()
        self.assertEqual(task.status, 'todo')  # Status unchanged

    def test_delete_task_creator(self):
        """Test task creator can delete their task"""
        task = Task.objects.create(
            title='Test Task',
            workspace=self.workspace,
            assigned_to=self.user2,
            created_by=self.user1
        )

        self.client.login(username='user1', password='TestPass123')
        response = self.client.post(reverse('delete_task', args=[task.id]))

        self.assertFalse(Task.objects.filter(id=task.id).exists())

    def test_delete_task_workspace_admin(self):
        """Test workspace admin can delete any team task"""
        task = Task.objects.create(
            title='Test Task',
            workspace=self.workspace,
            assigned_to=self.user2,
            created_by=self.user2
        )

        self.client.login(username='user1', password='TestPass123')
        response = self.client.post(reverse('delete_task', args=[task.id]))

        self.assertFalse(Task.objects.filter(id=task.id).exists())

    def test_non_creator_cannot_delete_task(self):
        """Test that non-creators/non-admins cannot delete tasks"""
        task = Task.objects.create(
            title='Test Task',
            workspace=self.workspace,
            assigned_to=self.user2,
            created_by=self.user1
        )

        self.client.login(username='user2', password='TestPass123')
        response = self.client.post(reverse('delete_task', args=[task.id]))

        self.assertTrue(Task.objects.filter(id=task.id).exists())

    def test_my_tasks_page_shows_assigned_tasks(self):
        """Test my tasks page shows all tasks assigned to user"""
        # Create tasks
        task1 = Task.objects.create(
            title='Task 1',
            workspace=self.workspace,
            assigned_to=self.user2,
            created_by=self.user1
        )
        task2 = Task.objects.create(
            title='Task 2',
            assigned_to=self.user2,
            created_by=self.user1,
            is_personal=True
        )

        self.client.login(username='user2', password='TestPass123')
        response = self.client.get(reverse('my_tasks'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('all_tasks', response.context)
        self.assertEqual(len(response.context['all_tasks']), 2)

    def test_my_tasks_filter_by_status(self):
        """Test filtering tasks by status on my tasks page"""
        Task.objects.create(
            title='Todo Task',
            assigned_to=self.user2,
            created_by=self.user1,
            status='todo'
        )
        Task.objects.create(
            title='Done Task',
            assigned_to=self.user2,
            created_by=self.user1,
            status='done'
        )

        self.client.login(username='user2', password='TestPass123')
        response = self.client.get(reverse('my_tasks') + '?status=todo')

        self.assertEqual(len(response.context['all_tasks']), 1)
        self.assertEqual(response.context['all_tasks'][0].title, 'Todo Task')

    def test_workspace_task_completion_percentage(self):
        """Test workspace get_task_completion_percentage method"""
        # Create 10 tasks, complete 7
        for i in range(10):
            status = 'done' if i < 7 else 'todo'
            Task.objects.create(
                title=f'Task {i}',
                workspace=self.workspace,
                assigned_to=self.user2,
                created_by=self.user1,
                status=status
            )

        percentage = self.workspace.get_task_completion_percentage()
        self.assertEqual(percentage, 70)

    def test_workspace_task_completion_percentage_zero_tasks(self):
        """Test workspace completion percentage with no tasks"""
        percentage = self.workspace.get_task_completion_percentage()
        self.assertEqual(percentage, 0)

    def test_task_form_with_workspace(self):
        """Test TaskForm initializes with workspace members"""
        form = TaskForm(workspace=self.workspace)

        # Check that assigned_to field has workspace members as choices
        choices = form.fields['assigned_to'].choices
        self.assertTrue(len(choices) > 0)

    def test_task_with_due_date(self):
        """Test creating task with due date"""
        from datetime import date, timedelta
        due_date = date.today() + timedelta(days=7)

        task = Task.objects.create(
            title='Task with due date',
            workspace=self.workspace,
            assigned_to=self.user2,
            created_by=self.user1,
            due_date=due_date
        )

        self.assertEqual(task.due_date, due_date)

    def test_task_str_representation(self):
        """Test Task string representation"""
        task = Task.objects.create(
            title='Test Task',
            workspace=self.workspace,
            assigned_to=self.user2,
            created_by=self.user1
        )

        expected = f'Test Task (To Do)'
        self.assertEqual(str(task), expected)

    def test_task_status_choices(self):
        """Test that task has correct status choices"""
        self.assertEqual(Task.STATUS_CHOICES, [
            ('todo', 'To Do'),
            ('in_progress', 'In Progress'),
            ('done', 'Done'),
        ])

    def test_my_tasks_progress_calculation(self):
        """Test progress calculation on my tasks page"""
        # Create 5 tasks, complete 2
        for i in range(5):
            status = 'done' if i < 2 else 'todo'
            Task.objects.create(
                title=f'Task {i}',
                assigned_to=self.user2,
                created_by=self.user1,
                status=status
            )

        self.client.login(username='user2', password='TestPass123')
        response = self.client.get(reverse('my_tasks'))

        self.assertEqual(response.context['total_tasks'], 5)
        self.assertEqual(response.context['completed_tasks'], 2)
        self.assertEqual(response.context['progress_percentage'], 40)

    def test_create_task_requires_workspace_membership(self):
        """Test that only workspace members can create tasks"""
        user3 = User.objects.create_user(username='user3', password='TestPass123')
        UserProfile.objects.create(user=user3, display_name='User Three')

        self.client.login(username='user3', password='TestPass123')
        response = self.client.post(reverse('create_task', args=[self.workspace.id]), {
            'title': 'Unauthorized Task',
        })

        # Should redirect with error
        self.assertFalse(Task.objects.filter(title='Unauthorized Task').exists())
