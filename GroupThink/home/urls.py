from django.urls import path
from . import views

urlpatterns = [
    # Homepage
    path('', views.index, name='index'),

    # Authentication
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),

    # Workspaces/Teams
    path('workspace/create/', views.create_workspace, name='create_workspace'),
    path('workspace/join/', views.join_workspace, name='join_workspace'),
    path('workspace/<int:workspace_id>/', views.workspace_detail, name='workspace_detail'),
    path('workspace/<int:workspace_id>/toggle-code-visibility/', views.toggle_code_visibility, name='toggle_code_visibility'),
    path('workspace/<int:workspace_id>/remove-member/<int:user_id>/', views.remove_member, name='remove_member'),
    path('workspace/<int:pk>/delete/', views.delete_workspace, name='delete_workspace'),

    # Meetings
    path('create_meeting/', views.create_meeting, name='create_meeting'),
    path('join_meeting/<str:room_name>/', views.join_meeting, name='join_meeting'),
    path('meeting/<int:meeting_id>/delete/', views.delete_meeting, name='delete_meeting'),
    path('meeting/<int:meeting_id>/update-status/', views.update_meeting_status, name='update_meeting_status'),
    path('meeting/<int:meeting_id>/generate-tasks/', views.generate_tasks_from_meeting, name='generate_tasks_from_meeting'),

    # Tasks
    path('my-tasks/', views.my_tasks, name='my_tasks'),
    path('workspace/<int:workspace_id>/create-task/', views.create_task, name='create_task'),
    path('task/<int:task_id>/update-status/', views.update_task_status, name='update_task_status'),
    path('task/<int:task_id>/delete/', views.delete_task, name='delete_task'),

    # Webhooks
    path("webhooks/jaas/", views.jaas_webhook),

    # Transcriptions
    path("transcripts/<str:room_name>/", views.get_transcript, name="get_transcript"),

    # Recordings
    path("my-recordings/", views.my_recordings, name="my_recordings"),
    path("recordings/<int:pk>/", views.recording_detail, name="recording_detail"),
]