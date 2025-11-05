from django.db import models
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string
import uuid


class UserProfile(models.Model):
    """Extended user profile with additional information"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    display_name = models.CharField(max_length=100)
    email_verified = models.BooleanField(default=False)
    verification_token = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.display_name}"


class Workspace(models.Model):
    """Team for collaboration"""
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_workspaces')
    invite_code = models.CharField(max_length=20, unique=True, blank=True)
    code_visible_to_members = models.BooleanField(default=False)  # Admin controls code visibility
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.invite_code:
            # Generate a unique 8-character invite code
            self.invite_code = get_random_string(8).upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def get_task_completion_percentage(self):
        """Calculate percentage of completed tasks"""
        total_tasks = self.tasks.count()
        if total_tasks == 0:
            return 0
        completed_tasks = self.tasks.filter(status='done').count()
        return int((completed_tasks / total_tasks) * 100)

    def get_total_tasks(self):
        """Get total number of tasks"""
        return self.tasks.count()

    def get_completed_tasks(self):
        """Get number of completed tasks"""
        return self.tasks.filter(status='done').count()

    def get_in_progress_tasks(self):
        """Get number of in-progress tasks"""
        return self.tasks.filter(status='in_progress').count()


class WorkspaceMembership(models.Model):
    """Track which users belong to which teams"""
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('member', 'Member'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='workspace_memberships')
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'workspace')

    def __str__(self):
        return f"{self.user.username} in {self.workspace.name} ({self.role})"


class Meeting(models.Model):
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('live', 'Live'),
        ('ended', 'Ended'),
    ]

    title = models.CharField(max_length=100)
    room_name = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_meetings', null=True, blank=True)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='meetings', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_started')
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    recording_url = models.URLField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.get_status_display()}"

class MeetingTranscriptChunk(models.Model):
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="chunks")
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    speaker = models.CharField(max_length=120, blank=True, default="")


class Task(models.Model):
    """Tasks that can be assigned to team members"""
    STATUS_CHOICES = [
        ('todo', 'To Do'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='tasks', null=True, blank=True)
    assigned_to = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assigned_tasks', null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_tasks')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='todo')
    due_date = models.DateField(null=True, blank=True)
    is_personal = models.BooleanField(default=False)  # Personal task vs team task
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    def mark_complete(self):
        """Mark task as complete"""
        from django.utils import timezone
        self.status = 'done'
        if not self.completed_at:
            self.completed_at = timezone.now()
        self.save()

    def get_status_color(self):
        """Return color for status badge"""
        colors = {
            'todo': '#f59e0b',      # Yellow
            'in_progress': '#3b82f6',  # Blue
            'done': '#22c55e',      # Green
        }
        return colors.get(self.status, '#gray')


