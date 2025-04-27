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
    Custom permission to only allow marked student users.
    This checks if the user *is* a marked student.
    """

    def has_permission(self, request, view):
        # Check if the user is authenticated and is a student
        if not (
            request.user and request.user.is_authenticated and request.user.is_student()
        ):
            return False  # Not authenticated or not a student

        # Check if the student is marked
        return request.user.is_marked

    # object-level permission not needed for this check


class IsNotMarkedStudent(BasePermission):
    """
    Custom permission to only allow students who are NOT marked.
    """

    def has_permission(self, request, view):
        # Check if the user is authenticated and is a student
        if not (
            request.user and request.user.is_authenticated and request.user.is_student()
        ):
            return False  # Not authenticated or not a student

        # Check if the student is NOT marked
        return not request.user.is_marked  # This is the key difference

    # object-level permission not needed for this check


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
