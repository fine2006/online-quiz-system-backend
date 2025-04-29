# quiz_frontend/urls.py

from django.urls import path
from . import views  # Import views from the current app

urlpatterns = [
    # Homepage URL pattern
    path("", views.index, name="index"),
    # Quiz list page URL pattern
    path("quizzes/", views.quiz_list_view, name="quiz_list"),
    # User-specific pages (from Part 1)
    path("profile/", views.profile_view, name="profile"),
    path("attempts/", views.attempt_list_view, name="attempt_list"),
    path(
        "attempts/<int:pk>/results/", views.attempt_detail_view, name="attempt_detail"
    ),
    # Add URL pattern for the Quiz Detail / Taking page (Part 2)
    # This URL takes an integer 'pk' which is the Quiz ID
    path("quizzes/<int:pk>/take/", views.quiz_detail_view, name="quiz_detail"),
    # Add URL patterns for any other frontend pages here as you create more views
]
