# core/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing, name='landing'),
    path('horario', views.horario, name='horario'),
    path('leaderboard', views.leaderboard, name='leaderboard'),
    path('eventos', views.eventos, name='eventos'),
    path('atletas', views.athletes, name='athletes'),
    path('sponsors', views.sponsors, name='sponsors'),
    path('info-lugar', views.venue_info, name='venue_info'),
    path('staff/scores', views.staff_scores, name='staff_scores'),
    path('staff/schedule', views.staff_schedule, name='staff_schedule'),
    path('me', views.my_day, name='my_day'),
]
