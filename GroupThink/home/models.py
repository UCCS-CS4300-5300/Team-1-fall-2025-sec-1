from django.db import models
import uuid

class Meeting(models.Model):
    title = models.CharField(max_length=100)
    room_name = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)


