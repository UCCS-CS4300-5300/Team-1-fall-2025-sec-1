from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('create_meeting/', views.create_meeting, name='create_meeting'),
    path('join_meeting/<str:room_name>/', views.join_meeting, name='join_meeting'),
]