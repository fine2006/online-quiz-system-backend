# quiz_app/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, AllowAny, IsAuthenticated
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import (
    CustomUser,
    Quiz,
    QuizAttempt,
    ParticipantAnswer,
    Roles,
    QuestionTypes,
)
from .serializers import (
    UserSerializer,
    QuizWritableSerializer,
    QuizReadOnlySerializer,
    QuizSubmissionSerializer,
    QuizAttemptResultSerializer,
    ParticipantAnswerResultSerializer,  # Import needed for potential direct use or context
)
from .permissions import (
    IsTeacherOrAdmin,
    IsStudent,
    IsMarkedStudent,
    IsQuizTeacherOrAdmin,
    IsAttemptOwnerOrTeacherOrAdmin,
)

from dj_rest_auth.registration.views import SocialLoginView
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client


class CustomGoogleOAuth2Client(OAuth2Client):
    def __init__(
        self,
        request,
        consumer_key,
        consumer_secret,
        access_token_method,
        access_token_url,
        callback_url,
        _scope,  # This is fix for incompatibility between django-allauth==65.3.1 and dj-rest-auth==7.0.1
        scope_delimiter=" ",
        headers=None,
        basic_auth=False,
    ):
        super().__init__(
            request,
            consumer_key,
            consumer_secret,
            access_token_method,
            access_token_url,
            callback_url,
            scope_delimiter,
            headers,
            basic_auth,
        )


class GoogleLoginView(SocialLoginView):
    """
    Custom SocialLoginView for Google OAuth2.
    Configures the adapter_class attribute for SocialLoginView.
    """

    adapter_class = GoogleOAuth2Adapter
    client_class = CustomGoogleOAuth2Client
    # callback_url = "http://localhost:8000/accounts/google/login/callback/"


# If you put this in quiz_app/views.py, no extra imports are needed in urls.py
# If you created a new file like quiz_app/auth_views.py, you'll import from there.


class UserViewSet(viewsets.ModelViewSet):
    queryset = CustomUser.objects.all().order_by(
        "id"
    )  # Order for consistent pagination
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]  # Only Admins can CRUD users

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, IsTeacherOrAdmin],
    )
    def mark_student(self, request, pk=None):
        """Mark a student user."""
        user = self.get_object()
        if not user.is_student():
            return Response(
                {"detail": "Only student users can be marked."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_marked = True
        user.save()
        return Response({"status": "student marked"}, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, IsTeacherOrAdmin],
    )
    def unmark_student(self, request, pk=None):
        """Unmark a student user."""
        user = self.get_object()
        if not user.is_student():
            return Response(
                {"detail": "Only student users can be unmarked."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_marked = False
        user.save()
        return Response({"status": "student unmarked"}, status=status.HTTP_200_OK)


class QuizViewSet(viewsets.ModelViewSet):
    queryset = (
        Quiz.objects.prefetch_related("questions__answer_options").all().order_by("id")
    )
    # serializer_class will be determined by get_serializer_class
    # permission_classes will be determined by get_permissions

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return QuizWritableSerializer
        # For list, retrieve, and the submit action, use the read-only serializer
        return QuizReadOnlySerializer

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        if self.action in ["create"]:
            # Only authenticated Teachers and Admins can create quizzes
            return [IsAuthenticated(), IsTeacherOrAdmin()]
        elif self.action in ["update", "partial_update", "destroy"]:
            # Only authenticated Teachers and Admins can update/delete quizzes,
            # AND they must be the owner (or Admin).
            return [IsAuthenticated(), IsTeacherOrAdmin(), IsQuizTeacherOrAdmin()]
        elif self.action == "submit":
            # Only authenticated Students who are NOT marked can submit
            return [IsAuthenticated(), IsStudent(), ~IsMarkedStudent()]
        else:  # list, retrieve, and any other actions
            # Allow any user (authenticated or unauthenticated) to list/retrieve quizzes
            return [AllowAny()]

    def perform_create(self, serializer):
        # Assign the logged-in user as the teacher for the quiz
        serializer.save(teacher=self.request.user)

    @action(detail=True, methods=["post"], serializer_class=QuizSubmissionSerializer)
    def submit(self, request, pk=None):
        """Handles quiz submission from a student."""
        quiz = (
            self.get_object()
        )  # get_object applies object-level permissions if any are set for this action

        # The permission class IsStudent and ~IsMarkedStudent already check the user role and marked status.

        # Validate the submission payload
        # Pass the quiz instance to the serializer context if needed for specific validation
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data
        answers_data = validated_data["answers"]

        # Ensure quiz_id in the payload matches the URL pk (detail=True)
        if validated_data["quiz_id"] != int(pk):
            return Response(
                {"detail": "Quiz ID in payload does not match URL."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Double-check availability (can be done in serializer validation too, doing both for safety)
        if not quiz.is_available_for_submission:
            return Response(
                {"detail": "This quiz is not currently available for submission."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Use a transaction for atomicity
        with transaction.atomic():
            # Create the QuizAttempt
            attempt = QuizAttempt.objects.create(user=request.user, quiz=quiz)

            # Process each submitted answer
            for answer_data in answers_data:
                question_id = answer_data["question_id"]
                selected_option_ids = answer_data.get("selected_option_ids", [])
                selected_answer_bool = answer_data.get("selected_answer_bool")

                # Fetch the question (already validated to exist and belong to the quiz by the serializer)
                question = quiz.questions.get(
                    id=question_id
                )  # Use get() as we know it exists

                # Create the ParticipantAnswer
                participant_answer = ParticipantAnswer.objects.create(
                    attempt=attempt,
                    question=question,
                    selected_answer_bool=selected_answer_bool,  # Set boolean answer
                )

                # Set selected options for MCQ types
                if selected_option_ids:
                    selected_options = AnswerOption.objects.filter(
                        id__in=selected_option_ids
                    )
                    participant_answer.selected_options.set(selected_options)

                # Determine and save the correctness of the answer
                participant_answer.determine_correctness()  # This also calls save()

            # Calculate and save the overall score for the attempt
            attempt.calculate_score()  # This also calls save()

        # Return the results of the attempt
        result_serializer = QuizAttemptResultSerializer(attempt)
        return Response(result_serializer.data, status=status.HTTP_201_CREATED)


class QuizAttemptViewSet(viewsets.ReadOnlyModelViewSet):
    # ReadOnlyModelViewSet as attempts are created via the Quiz submit action
    queryset = (
        QuizAttempt.objects.select_related("user", "quiz")
        .prefetch_related(
            "participant_answers__question__answer_options",  # Prefetch for ParticipantAnswerResultSerializer
            "participant_answers__selected_options",  # Prefetch selected options
        )
        .all()
        .order_by("-submission_time")
    )  # Order by most recent attempt first

    serializer_class = QuizAttemptResultSerializer
    # Permissions handled by get_permissions and get_queryset

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        # Authenticated users (Students, Teachers, Admins) can view attempts.
        # Marked students can view *their own* attempts.
        # Object-level permission handled by IsAttemptOwnerOrTeacherOrAdmin for retrieve.
        return [
            IsAuthenticated(),
            IsAttemptOwnerOrTeacherOrAdmin(),
        ]  # Check object perm for retrieve

    def get_queryset(self):
        """
        Filters attempts based on user role. Students see only their own.
        Teachers/Admins see all.
        """
        user = self.request.user
        if user.is_authenticated:
            if user.is_student():
                # Students only see their own attempts
                return self.queryset.filter(user=user)
            else:  # Teacher or Admin
                # Teachers and Admins see all attempts
                return self.queryset.all()
        # Unauthenticated users should not see attempts (handled by IsAuthenticated)
        return self.queryset.none()

    # No need to override `retrieve` explicitly if `IsAttemptOwnerOrTeacherOrAdmin`
    # is in `get_permissions` and `get_object()` is used (which it is by default).
    # get_object() will fetch based on the filtered queryset, and then check object permissions.
