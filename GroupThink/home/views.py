from django.shortcuts import render, redirect
from .models import Meeting
import uuid, os
from .jaas_functions import generate_jaas_token

# Create your views here.
def index(request):
    """Renders home page"""
    return render(request, 'home/index.html')

def create_meeting(request):
    """Renders create meeting page, can redirect to join meeting if meeting created"""

    if request.method == 'POST':
        meeting = Meeting.objects.create(title=request.POST.get('title'), 
            room_name=f"groupthink-{uuid.uuid4().hex[:10]}")
        return redirect('join_meeting', room_name=meeting.room_name)

    return render(request, 'home/create_meeting.html')

def join_meeting(request, room_name):
    """Directs user to meeting page"""

    meeting = Meeting.objects.get(room_name=room_name)
    token = generate_jaas_token(room_name)
    app_id = os.getenv('JAAS_APP_ID')
    full_room_name = f"{app_id}/{room_name}"

    return render(request, 'home/join_meeting.html', {'meeting': meeting, 'token': token, 'app_id': app_id, 
        'room_name': full_room_name})
