"""Admin configuration for GroupThink models."""
from django.contrib import admin

from .models import Meeting, Task, UserProfile, Workspace, WorkspaceMembership


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin configuration for UserProfile model."""
    list_display = ('user', 'display_name', 'email_verified', 'created_at')
    list_filter = ('email_verified', 'created_at')
    search_fields = ('user__username', 'user__email', 'display_name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    """Admin configuration for Workspace model."""
    list_display = (
        'name', 'created_by', 'invite_code', 'code_visible_to_members', 'created_at'
    )
    list_filter = ('created_at', 'code_visible_to_members')
    search_fields = ('name', 'invite_code', 'created_by__username')
    readonly_fields = ('created_at', 'updated_at', 'invite_code')
    list_editable = ('code_visible_to_members',)


@admin.register(WorkspaceMembership)
class WorkspaceMembershipAdmin(admin.ModelAdmin):
    """Admin configuration for WorkspaceMembership model."""
    list_display = ('user', 'workspace', 'role', 'joined_at')
    list_filter = ('role', 'joined_at')
    search_fields = ('user__username', 'workspace__name')
    readonly_fields = ('joined_at',)


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    """Admin configuration for Meeting model."""
    list_display = ('title', 'room_name', 'status', 'created_by', 'workspace', 'created_at')
    list_filter = ('created_at', 'status', 'workspace')
    search_fields = ('title', 'room_name', 'created_by__username')
    readonly_fields = ('created_at', 'room_name')
    list_editable = ('status',)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    """Admin configuration for Task model."""
    list_display = (
        'title', 'workspace', 'assigned_to', 'status',
        'is_personal', 'due_date', 'created_by'
    )
    list_filter = ('status', 'is_personal', 'workspace', 'created_at')
    search_fields = ('title', 'description', 'assigned_to__username', 'created_by__username')
    readonly_fields = ('created_at', 'updated_at', 'completed_at')
    list_editable = ('status',)
