# quiz_app/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, QuizViewSet, QuizAttemptViewSet

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")
router.register(r"quizzes", QuizViewSet, basename="quiz")
router.register(r"attempts", QuizAttemptViewSet, basename="attempt")

urlpatterns = [
    path("", include(router.urls)),
]
