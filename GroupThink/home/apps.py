"""Application configuration for the home app."""
from django.apps import AppConfig


class HomeConfig(AppConfig):
    """Configuration class for the home application."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'home'
