from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.utils.crypto import get_random_string
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from .meeting_ai import extract_tasks_from_meeting
from .recording_webhook_handlers import handle_recording_uploaded

# from django.core.mail import send_mail  # For future email verification
# from django.conf import settings  # For future email verification

from .models import (
    Meeting,
    UserProfile,
    Workspace,
    WorkspaceMembership,
    Task,
    MeetingTranscriptChunk,
    Recording,
    ChatMessage,
    ChatAttachment
)
from .forms import (
    SignUpForm,
    LoginForm,
    WorkspaceForm,
    JoinWorkspaceForm,
    TaskForm,
)
from .jaas_functions import generate_jaas_token

import uuid
import os
import json

# Create your views here.
def index(request):
    """Renders home page, redirects to dashboard if logged in"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'home/index.html')


# ============ AUTHENTICATION VIEWS ============

def signup_view(request):
    """User registration with email verification"""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            # Create user but don't activate yet
            user = form.save(commit=False)
            user.email = form.cleaned_data['email']
            user.is_active = True  # For now, skip email verification
            user.save()

            # Create user profile
            verification_token = get_random_string(64)
            UserProfile.objects.create(
                user=user,
                display_name=form.cleaned_data['display_name'],
                verification_token=verification_token,
                email_verified=False  # Will implement email verification
            )

            # Send verification email (placeholder for now)
            # TODO: Implement actual email verification
            # verification_link = request.build_absolute_uri(f'/verify-email/{verification_token}/')
            # send_mail(
            #     'Verify your GroupThink account',
            #     f'Click here to verify: {verification_link}',
            #     settings.DEFAULT_FROM_EMAIL,
            #     [user.email],
            # )

            messages.success(request, 'Account created successfully! You can now log in.')
            return redirect('login')
    else:
        form = SignUpForm()

    return render(request, 'home/signup.html', {'form': form})


def login_view(request):
    """User login with session management"""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username_or_email = form.cleaned_data['username']
            password = form.cleaned_data['password']
            remember_me = form.cleaned_data.get('remember_me', False)

            # Check if user entered email instead of username
            user = None
            if '@' in username_or_email:
                try:
                    user_obj = User.objects.get(email=username_or_email)
                    username = user_obj.username
                except User.DoesNotExist:
                    username = username_or_email
            else:
                username = username_or_email

            # Authenticate user
            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)

                # ✅ Ensure profile exists to prevent "User has no profile" error
                from home.models import UserProfile
                profile, _ = UserProfile.objects.get_or_create(
                    user=user,
                    defaults={"display_name": user.username}
                )

                # Set session expiry
                if not remember_me:
                    request.session.set_expiry(0)  # Session expires when browser closes
                else:
                    request.session.set_expiry(1209600)  # 2 weeks

                messages.success(request, f'Welcome back, {profile.display_name}!')
                return redirect('dashboard')
            else:
                messages.error(request, 'Invalid username/email or password.')
    else:
        form = LoginForm()

    return render(request, 'home/login.html', {'form': form})


@login_required
def logout_view(request):
    """User logout"""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('index')


# ============ DASHBOARD & WORKSPACE VIEWS ============

@login_required
def dashboard(request):
    """User dashboard showing all workspaces"""
    # Get all workspaces user is a member of
    memberships = request.user.workspace_memberships.select_related('workspace').all()
    workspaces = [m.workspace for m in memberships]

    # Get owned workspaces
    owned_workspaces = request.user.owned_workspaces.all()

    # Add task counts to each workspace for template
    for workspace in workspaces:
        workspace.total_tasks = workspace.tasks.count()
        workspace.completed_tasks = workspace.tasks.filter(status='done').count()

    # Calculate pending tasks for quick actions
    pending_tasks_count = request.user.assigned_tasks.exclude(status='done').count()

    context = {
        'workspaces': workspaces,
        'owned_workspaces': owned_workspaces,
        'user_profile': request.user.profile,
        'pending_tasks_count': pending_tasks_count,
    }
    return render(request, 'home/dashboard.html', context)


@login_required
def create_workspace(request):
    """Create a new workspace"""
    if request.method == 'POST':
        form = WorkspaceForm(request.POST)
        if form.is_valid():
            workspace = Workspace.objects.create(
                name=form.cleaned_data['name'],
                created_by=request.user
            )
            # Add creator as admin member
            WorkspaceMembership.objects.create(
                user=request.user,
                workspace=workspace,
                role='admin'
            )
            messages.success(request, f'Workspace "{workspace.name}" created! Invite code: {workspace.invite_code}')
            return redirect('workspace_detail', workspace_id=workspace.id)
    else:
        form = WorkspaceForm()

    return render(request, 'home/create_workspace.html', {'form': form})


@login_required
def join_workspace(request):
    """Join a workspace using invite code"""
    if request.method == 'POST':
        form = JoinWorkspaceForm(request.POST)
        if form.is_valid():
            invite_code = form.cleaned_data['invite_code']
            try:
                workspace = Workspace.objects.get(invite_code=invite_code)

                # Check if already a member
                if WorkspaceMembership.objects.filter(user=request.user, workspace=workspace).exists():
                    messages.warning(request, f'You are already a member of "{workspace.name}".')
                else:
                    WorkspaceMembership.objects.create(
                        user=request.user,
                        workspace=workspace,
                        role='member'
                    )
                    messages.success(request, f'Successfully joined "{workspace.name}"!')

                return redirect('workspace_detail', workspace_id=workspace.id)
            except Workspace.DoesNotExist:
                messages.error(request, 'Invalid invite code.')
    else:
        form = JoinWorkspaceForm()

    return render(request, 'home/join_workspace.html', {'form': form})


@login_required
def workspace_detail(request, workspace_id):
    """View workspace details and meetings"""
    workspace = get_object_or_404(Workspace, id=workspace_id)

    # Check if user is a member
    membership = WorkspaceMembership.objects.filter(user=request.user, workspace=workspace).first()
    if not membership:
        messages.error(request, 'You do not have access to this workspace.')
        return redirect('dashboard')

    # Get all meetings in this workspace
    meetings = workspace.meetings.all().order_by('-created_at')
    members = workspace.memberships.select_related('user', 'user__profile').all()

    context = {
        'workspace': workspace,
        'membership': membership,
        'meetings': meetings,
        'members': members,
    }
    return render(request, 'home/workspace_detail.html', context)


# ============ MEETING VIEWS (Updated) ============

@login_required
def create_meeting(request):
    """Renders create meeting page, can redirect to join meeting if meeting created"""
    # Get user's workspaces for dropdown
    memberships = request.user.workspace_memberships.select_related('workspace').all()
    workspaces = [m.workspace for m in memberships]

    if request.method == 'POST':
        workspace_id = request.POST.get('workspace')
        workspace = None

        if workspace_id:
            workspace = get_object_or_404(Workspace, id=workspace_id)
            # Verify user is a member
            if not WorkspaceMembership.objects.filter(user=request.user, workspace=workspace).exists():
                messages.error(request, 'You do not have access to this workspace.')
                return redirect('create_meeting')

        meeting = Meeting.objects.create(
            title=request.POST.get('title'),
            room_name=f"groupthink-{uuid.uuid4().hex[:10]}",
            created_by=request.user,
            workspace=workspace
        )
        return redirect('join_meeting', room_name=meeting.room_name)

    return render(request, 'home/create_meeting.html', {'workspaces': workspaces})


@login_required
def join_meeting(request, room_name):
    """Directs user to meeting page"""
    meeting = get_object_or_404(Meeting, room_name=room_name)

    # Check if user has access (either through workspace or if meeting has no workspace)
    if meeting.workspace:
        if not WorkspaceMembership.objects.filter(user=request.user, workspace=meeting.workspace).exists():
            messages.error(request, 'You do not have access to this meeting.')
            return redirect('dashboard')

    meeting.participants.add(request.user)

    token = generate_jaas_token(room_name)
    app_id = os.getenv('JAAS_APP_ID')
    full_room_name = f"{app_id}/{room_name}"

    return render(request, 'home/join_meeting.html', {
        'meeting': meeting,
        'token': token,
        'app_id': app_id,
        'room_name': full_room_name
    })


# ============ NEW FEATURES: Meeting Management ============
@login_required
def generate_tasks_from_meeting(request, meeting_id):
    """
    Use AI to extract tasks from a meeting's transcript and create Task rows.
    """
    print("=== STARTING TASK GENERATION ===")
    meeting = get_object_or_404(Meeting, id=meeting_id)

    # Permission check
    is_creator = meeting.created_by == request.user
    is_workspace_member = False
    if meeting.workspace:
        is_workspace_member = WorkspaceMembership.objects.filter(
            user=request.user,
            workspace=meeting.workspace
        ).exists()

    if not (is_creator or is_workspace_member):
        messages.error(request, "You do not have permission to generate tasks for this meeting.")
        return redirect('dashboard')

    if request.method != "POST":
        return HttpResponseForbidden("Invalid request method.")

    print("=== CALLING EXTRACT_TASKS_FROM_MEETING ===")
    try:
        result = extract_tasks_from_meeting(meeting.id, request.user.id)
        print(f"=== RESULT: {result} ===")
    except Exception as e:
        import traceback
        print("=== FULL ERROR ===")
        print(traceback.format_exc())
        messages.error(request, f"AI task generation failed: {e}")
    else:
        created = result.get("created", 0)
        reason = result.get("reason")
        if created:
            messages.success(request, f"Generated {created} task(s) from meeting transcript.")
        elif reason:
            messages.info(request, reason)
        else:
            messages.info(request, "No tasks were created from the transcript.")

    if meeting.workspace:
        return redirect('workspace_detail', workspace_id=meeting.workspace.id)
    return redirect('dashboard')

@login_required
def delete_meeting(request, meeting_id):
    """Delete a meeting (creator only)"""
    meeting = get_object_or_404(Meeting, id=meeting_id)

    # Check if user is the creator or workspace admin
    is_creator = meeting.created_by == request.user
    is_workspace_admin = False

    if meeting.workspace:
        membership = WorkspaceMembership.objects.filter(
            user=request.user,
            workspace=meeting.workspace,
            role='admin'
        ).first()
        is_workspace_admin = membership is not None

    if not (is_creator or is_workspace_admin):
        messages.error(request, 'You do not have permission to delete this meeting.')
        return redirect('dashboard')

    workspace_id = meeting.workspace.id if meeting.workspace else None
    meeting_title = meeting.title
    meeting.delete()

    messages.success(request, f'Meeting "{meeting_title}" has been deleted.')

    if workspace_id:
        return redirect('workspace_detail', workspace_id=workspace_id)
    return redirect('dashboard')


@login_required
def update_meeting_status(request, meeting_id):
    """Update meeting status (Live, Not Started, Ended)"""
    meeting = get_object_or_404(Meeting, id=meeting_id)

    # Check if user is the creator or workspace admin
    is_creator = meeting.created_by == request.user
    is_workspace_admin = False

    if meeting.workspace:
        membership = WorkspaceMembership.objects.filter(
            user=request.user,
            workspace=meeting.workspace,
            role='admin'
        ).first()
        is_workspace_admin = membership is not None

    if not (is_creator or is_workspace_admin):
        messages.error(request, 'You do not have permission to update this meeting.')
        return redirect('dashboard')

    if request.method == 'POST':
        from django.utils import timezone
        from django.http import HttpResponse
        new_status = request.POST.get('status')

        if new_status in ['not_started', 'live', 'ended']:
            meeting.status = new_status

            if new_status == 'live' and not meeting.started_at:
                meeting.started_at = timezone.now()
            elif new_status == 'ended' and not meeting.ended_at:
                meeting.ended_at = timezone.now()

            meeting.save()
            messages.success(request, f'Meeting status updated to "{meeting.get_status_display()}".')
        else:
            messages.error(request, 'Invalid status.')

        # If ending meeting, always go to dashboard
        if new_status == 'ended':
            return redirect('dashboard')

        # For marking as live (AJAX request), just return success
        # The JavaScript will handle reloading the page
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return HttpResponse('OK')

    # Default redirects
    if meeting.workspace:
        return redirect('workspace_detail', workspace_id=meeting.workspace.id)
    return redirect('dashboard')


# ============ NEW FEATURES: Team/Workspace Management ============

@login_required
def remove_member(request, workspace_id, user_id):
    """Remove a member from a workspace (admin only)"""
    workspace = get_object_or_404(Workspace, id=workspace_id)

    # Check if current user is admin
    admin_membership = WorkspaceMembership.objects.filter(
        user=request.user,
        workspace=workspace,
        role='admin'
    ).first()

    if not admin_membership:
        messages.error(request, 'You do not have permission to remove members.')
        return redirect('workspace_detail', workspace_id=workspace_id)

    # Get the membership to remove
    user_to_remove = get_object_or_404(User, id=user_id)
    membership_to_remove = WorkspaceMembership.objects.filter(
        user=user_to_remove,
        workspace=workspace
    ).first()

    if not membership_to_remove:
        messages.error(request, 'User is not a member of this workspace.')
        return redirect('workspace_detail', workspace_id=workspace_id)

    # Prevent removing the workspace creator
    if user_to_remove == workspace.created_by:
        messages.error(request, 'Cannot remove the workspace creator.')
        return redirect('workspace_detail', workspace_id=workspace_id)

    # Remove the membership
    username = user_to_remove.username
    membership_to_remove.delete()
    messages.success(request, f'Removed {username} from the workspace.')

    return redirect('workspace_detail', workspace_id=workspace_id)


@login_required
def toggle_code_visibility(request, workspace_id):
    """Toggle whether team members can see the invite code (admin only)"""
    workspace = get_object_or_404(Workspace, id=workspace_id)

    # Check if current user is admin
    admin_membership = WorkspaceMembership.objects.filter(
        user=request.user,
        workspace=workspace,
        role='admin'
    ).first()

    if not admin_membership:
        messages.error(request, 'You do not have permission to change code visibility.')
        return redirect('workspace_detail', workspace_id=workspace_id)

    # Toggle visibility
    workspace.code_visible_to_members = not workspace.code_visible_to_members
    workspace.save()

    if workspace.code_visible_to_members:
        messages.success(request, 'Invite code is now visible to all team members.')
    else:
        messages.success(request, 'Invite code is now visible to admins only.')

    return redirect('workspace_detail', workspace_id=workspace_id)

def delete_workspace(request, pk):
    workspace = get_object_or_404(Workspace, pk=pk)

    # Check if the current user is an admin of this workspace
    is_admin = WorkspaceMembership.objects.filter(
        workspace=workspace,
        user=request.user,
        role='admin'
    ).exists()

    if not is_admin:
        return HttpResponseForbidden("You are not allowed to delete this workspace.")

    if request.method == 'POST':
        workspace.delete()
        return redirect('dashboard')

    return HttpResponseForbidden("Invalid request.")


# ============ TASK MANAGEMENT VIEWS ============

@login_required
def my_tasks(request):
    """Show all tasks assigned to current user across all teams"""
    # Get all tasks assigned to the user
    all_tasks = Task.objects.filter(assigned_to=request.user).select_related('workspace', 'created_by').order_by('-created_at')

    # Filter by status if requested
    status_filter = request.GET.get('status', 'all')
    if status_filter != 'all':
        all_tasks = all_tasks.filter(status=status_filter)

    # Calculate overall progress
    total_tasks = Task.objects.filter(assigned_to=request.user).count()
    completed_tasks = Task.objects.filter(assigned_to=request.user, status='done').count()
    progress_percentage = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0

    # Group tasks by team
    team_tasks = {}
    personal_tasks = []

    for task in all_tasks:
        if task.is_personal or not task.workspace:
            personal_tasks.append(task)
        else:
            team_name = task.workspace.name
            if team_name not in team_tasks:
                team_tasks[team_name] = []
            team_tasks[team_name].append(task)

    context = {
        'all_tasks': all_tasks,
        'team_tasks': team_tasks,
        'personal_tasks': personal_tasks,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'progress_percentage': progress_percentage,
        'status_filter': status_filter,
    }
    return render(request, 'home/my_tasks.html', context)


@login_required
def create_task(request, workspace_id):
    """Create new task in team (admin only can assign, members can create personal tasks)"""
    workspace = get_object_or_404(Workspace, id=workspace_id)

    # Check if user is a member
    membership = WorkspaceMembership.objects.filter(user=request.user, workspace=workspace).first()
    if not membership:
        messages.error(request, 'You do not have access to this workspace.')
        return redirect('dashboard')

    if request.method == 'POST':
        form = TaskForm(request.POST, workspace=workspace)
        if form.is_valid():
            # Create the task
            assigned_to_id = form.cleaned_data.get('assigned_to')
            assigned_to = None

            if assigned_to_id:
                assigned_to = get_object_or_404(User, id=assigned_to_id)

            task = Task.objects.create(
                title=form.cleaned_data['title'],
                description=form.cleaned_data.get('description', ''),
                workspace=workspace if not form.cleaned_data.get('is_personal') else None,
                assigned_to=assigned_to,
                created_by=request.user,
                due_date=form.cleaned_data.get('due_date'),
                is_personal=form.cleaned_data.get('is_personal', False)
            )

            messages.success(request, f'Task "{task.title}" created successfully!')
            return redirect('workspace_detail', workspace_id=workspace.id)
    else:
        form = TaskForm(workspace=workspace)

    context = {
        'form': form,
        'workspace': workspace,
    }
    return render(request, 'home/create_task.html', context)


@login_required
def update_task_status(request, task_id):
    """Update task status (To Do, In Progress, Done)"""
    task = get_object_or_404(Task, id=task_id)

    # Check if user has permission (assigned to them, or they're admin of the workspace, or task creator)
    is_assigned = task.assigned_to == request.user
    is_creator = task.created_by == request.user
    is_admin = False

    if task.workspace:
        membership = WorkspaceMembership.objects.filter(
            user=request.user,
            workspace=task.workspace,
            role='admin'
        ).first()
        is_admin = membership is not None

    if not (is_assigned or is_creator or is_admin):
        messages.error(request, 'You do not have permission to update this task.')
        return redirect('dashboard')

    if request.method == 'POST':
        new_status = request.POST.get('status')

        if new_status in ['todo', 'in_progress', 'done']:
            task.status = new_status

            # Mark completion time if done
            if new_status == 'done':
                task.mark_complete()
            else:
                task.save()

            messages.success(request, f'Task status updated to "{task.get_status_display()}".')
        else:
            messages.error(request, 'Invalid status.')

    # Redirect back to appropriate page
    referer = request.META.get('HTTP_REFERER')
    if referer and 'my-tasks' in referer:
        return redirect('my_tasks')
    elif task.workspace:
        return redirect('workspace_detail', workspace_id=task.workspace.id)
    else:
        return redirect('my_tasks')


@login_required
def delete_task(request, task_id):
    """Delete a task (creator or workspace admin only)"""
    task = get_object_or_404(Task, id=task_id)

    # Check if user has permission
    is_creator = task.created_by == request.user
    is_admin = False

    if task.workspace:
        membership = WorkspaceMembership.objects.filter(
            user=request.user,
            workspace=task.workspace,
            role='admin'
        ).first()
        is_admin = membership is not None

    if not (is_creator or is_admin):
        messages.error(request, 'You do not have permission to delete this task.')
        return redirect('dashboard')

    workspace_id = task.workspace.id if task.workspace else None
    task_title = task.title
    task.delete()

    messages.success(request, f'Task "{task_title}" has been deleted.')

    # Redirect back to appropriate page
    referer = request.META.get('HTTP_REFERER')
    if referer and 'my-tasks' in referer:
        return redirect('my_tasks')
    elif workspace_id:
        return redirect('workspace_detail', workspace_id=workspace_id)
    else:
        return redirect('my_tasks')


# ============ ETC ============

# For recieving data from JaaS regarding transcripts
@csrf_exempt
def jaas_webhook(request):
    try:
        raw = request.body.decode("utf-8")
    except Exception:
        raw = ""
    print("WEBHOOK RAW:", raw[:400])

    try:
        payload = json.loads(raw or "{}")
    except Exception as e:
        print("WEBHOOK JSON ERROR:", repr(e))
        payload = {}

    event = payload.get("eventType")

    # ---- ROOM IDENT ----
    data = payload.get("data") or {}
    # fqn is TOP-LEVEL in your logs; keep robust fallbacks too
    room_full = (
        payload.get("fqn")              
        or data.get("fqn")              
        or data.get("roomName")         
        or payload.get("roomName")      
        or data.get("room")             
        or ""
    ).strip()

    room_slug = room_full.rsplit("/", 1)[-1] if room_full else ""

    # ---- TEXT ----
    text = (data.get("final") or data.get("stable") or data.get("text") or "").strip()
    participant = data.get("participant") or {}
    speaker = participant.get("name") or participant.get("id") or ""

    print(f"WEBHOOK PARSED: event={event!r} slug={room_slug!r} text_head={text[:80]!r}")

    if event == "TRANSCRIPTION_CHUNK_RECEIVED" and room_slug and text:
        from .models import Meeting
        m = Meeting.objects.filter(room_name=room_slug).first()
        if not m:
            print("WEBHOOK NO MEETING:", room_slug)
        else:
            m.chunks.create(text=text, speaker=speaker)
            print("WEBHOOK SAVED → meeting_id:", m.id)

    if event == "RECORDING_UPLOADED":
        handle_recording_uploaded(room_full, data)

    return JsonResponse({"ok": True})

# Grabs transcript data to send to live transcription text box
def get_transcript(request, room_name: str):
    slug = (room_name or "").rsplit("/", 1)[-1]
    meeting = get_object_or_404(Meeting, room_name=slug)

    # Prints in order of time said
    rows = meeting.chunks.order_by("created_at").values_list("speaker", "text")
    lines = []

    # Ensures to give each line its appropriate speaker.
    for speaker, text in rows:
        name = (speaker or "Unknown").strip()
        lines.append(f"{name}: {text}")
    return HttpResponse("\n".join(lines), content_type="text/plain")

@login_required
def my_recordings(request):
    user = request.user

    recordings = (
        Recording.objects
        .filter(meeting__participants=user)
        .select_related("meeting")
        .order_by("-created_at")
    )

    return render(request, "home/my_recordings.html", {
        "recordings": recordings,
    })

@login_required
def recording_detail(request, pk):
    recording = get_object_or_404(Recording, pk=pk)
    meeting = recording.meeting
    user = request.user

    is_participant = meeting.participants.filter(id=user.id).exists()
    is_creator = (meeting.created_by_id == user.id)

    if not (is_participant or is_creator):
        messages.error(request, "You do not have access to this recording.")
        return redirect("my_recordings")

    chunks = meeting.chunks.order_by("created_at")

    return render(request, "home/recording_detail.html", {
        "recording": recording,
        "meeting": meeting,
        "chunks": chunks,
    })


# ============ CHAT FUNCTIONALITY ============

@login_required
def send_chat_message(request, workspace_id):
    """Send a chat message to workspace (with optional file attachment)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST request required'}, status=400)

    workspace = get_object_or_404(Workspace, id=workspace_id)

    # Check if user is a member
    membership = WorkspaceMembership.objects.filter(user=request.user, workspace=workspace).first()
    if not membership:
        return JsonResponse({'error': 'You are not a member of this workspace'}, status=403)

    message_text = request.POST.get('message', '').strip()
    uploaded_file = request.FILES.get('file')

    # Validate that there's either a message or a file
    if not message_text and not uploaded_file:
        return JsonResponse({'error': 'Message or file required'}, status=400)

    # If no message text but there's a file, use a default message
    if not message_text and uploaded_file:
        message_text = f"[File: {uploaded_file.name}]"

    # Create the chat message
    chat_message = ChatMessage.objects.create(
        workspace=workspace,
        sender=request.user,
        message=message_text
    )

    # Handle file upload if present
    if uploaded_file:
        # Check file size (10MB = 10 * 1024 * 1024 bytes)
        max_size = 10 * 1024 * 1024
        if uploaded_file.size > max_size:
            chat_message.delete()
            return JsonResponse({'error': 'File size exceeds 10MB limit'}, status=400)

        # Create attachment
        ChatAttachment.objects.create(
            chat_message=chat_message,
            file=uploaded_file,
            file_name=uploaded_file.name,
            file_size=uploaded_file.size
        )

    return JsonResponse({
        'success': True,
        'message_id': chat_message.id,
        'sender': request.user.profile.display_name,
        'message': chat_message.message,
        'timestamp': chat_message.created_at.strftime('%b %d, %Y %I:%M %p')
    })


@login_required
def get_chat_messages(request, workspace_id):
    """Get all chat messages for a workspace"""
    workspace = get_object_or_404(Workspace, id=workspace_id)

    # Check if user is a member
    membership = WorkspaceMembership.objects.filter(user=request.user, workspace=workspace).first()
    if not membership:
        return JsonResponse({'error': 'You are not a member of this workspace'}, status=403)

    # Get messages after a certain ID if provided (for polling)
    since_id = request.GET.get('since_id', 0)
    messages_qs = workspace.chat_messages.filter(id__gt=since_id).select_related('sender', 'sender__profile')

    messages_data = []
    for msg in messages_qs:
        # Get attachments for this message
        attachments = []
        for attachment in msg.attachments.all():
            attachments.append({
                'id': attachment.id,
                'file_name': attachment.file_name,
                'file_url': attachment.file.url,
                'file_size': attachment.get_file_size_display()
            })

        messages_data.append({
            'id': msg.id,
            'sender': msg.sender.profile.display_name,
            'sender_username': msg.sender.username,
            'message': msg.message,
            'timestamp': msg.created_at.strftime('%b %d, %Y %I:%M %p'),
            'attachments': attachments,
            'is_own_message': msg.sender == request.user
        })

    return JsonResponse({'messages': messages_data})