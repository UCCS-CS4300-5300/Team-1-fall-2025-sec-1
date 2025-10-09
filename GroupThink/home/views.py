from django.shortcuts import render, redirect
from .models import Meeting
import uuid

# Create your views here.
def index(request):
    return render(request, 'home/index.html')

def create_meeting(request):

    if request.method == 'POST':
        meeting = Meeting.objects.create(title=request.POST.get('title'), 
            room_name=f"groupthink-{uuid.uuid4().hex[:10]}")
        return redirect('join_meeting', room_name=meeting.room_name)

    return render(request, 'home/create_meeting.html')

def join_meeting(request, room_name):
    meeting = Meeting.objects.get(room_name=room_name)

    return render(request, 'home/join_meeting.html', {'meeting': meeting})

