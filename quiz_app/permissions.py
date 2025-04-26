# quiz_app/permissions.py
from rest_framework.permissions import BasePermission, IsAuthenticated, IsAdminUser
from .models import Roles


class IsTeacherOrAdmin(BasePermission):
    """
    Allows access only to authenticated Teacher or Admin users.
    """

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and (request.user.role == Roles.TEACHER or request.user.role == Roles.ADMIN)
        )


class IsStudent(BasePermission):
    """
    Allows access only to authenticated Student users.
    """

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == Roles.STUDENT
        )


class IsMarkedStudent(BasePermission):
    """
    Denies access if the authenticated user is a marked student.
    This is typically used with `~IsMarkedStudent` in permission classes.
    """

    def has_permission(self, request, view):
        # This permission checks if the user *is* marked.
        # To deny access to marked students, you use `~IsMarkedStudent`.
        return request.user and request.user.is_authenticated and request.user.is_marked


class IsQuizTeacherOrAdmin(BasePermission):
    """
    Allows access only to the teacher who owns the quiz or an Admin.
    Applies to object-level permissions.
    """

    def has_object_permission(self, request, view, obj):
        # Assuming 'obj' is a Quiz instance
        if request.user and request.user.is_authenticated:
            if request.user.role == Roles.ADMIN:
                return True  # Admin can do anything
            if request.user.role == Roles.TEACHER and obj.teacher == request.user:
                return True  # Teacher can manage their own quizzes
        return False


class IsAttemptOwnerOrTeacherOrAdmin(BasePermission):
    """
    Allows access only to the owner of the attempt, the teacher of the quiz, or an Admin.
    Applies to object-level permissions for QuizAttempt.
    """

    def has_object_permission(self, request, view, obj):
        # Assuming 'obj' is a QuizAttempt instance
        if request.user and request.user.is_authenticated:
            if request.user.role == Roles.ADMIN:
                return True  # Admin can do anything
            if request.user.role == Roles.TEACHER and obj.quiz.teacher == request.user:
                return True  # Teacher can view attempts for their quizzes
            if request.user.role == Roles.STUDENT and obj.user == request.user:
                return True  # Student can view their own attempts
        return False
