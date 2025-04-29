# quiz_frontend/views.py

from django.shortcuts import render, get_object_or_404, redirect  # Import redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.urls import reverse  # Import reverse for redirecting to URLs by name
from django.db.models import Q

# Import models needed for these views
from quiz_app.models import (
    Quiz,
    QuizAttempt,
    ParticipantAnswer,
    Question,
    AnswerOption,
    QuestionTypes,
)  # Make sure QuestionTypes is imported
# --- Existing Views ---


def index(request):
    """
    View for the homepage.
    """
    context = {}
    return render(request, "quiz_frontend/index.html", context)


@login_required
def quiz_list_view(request):
    """
    View to display a list of quizzes available to the logged-in student.
    Includes quizzes with a set availability window and those with no window defined.
    """
    now = timezone.now()

    # Condition 1: Within the defined availability window
    available_by_dates = Q(available_from__lte=now, available_to__gte=now)

    # Condition 2: No availability window set (considered always available)
    available_by_default = Q(available_from__isnull=True, available_to__isnull=True)

    # Combine the conditions using OR (|) and filter the Quiz objects
    available_quizzes = Quiz.objects.filter(
        available_by_dates | available_by_default
    ).order_by("available_from")  # You can adjust ordering as needed

    context = {"quizzes": available_quizzes}
    return render(request, "quiz_frontend/quiz_list.html", context)


# --- New Views (Part 1 Features) ---


@login_required
def profile_view(request):
    """
    View to display the authenticated user's profile details.
    Fetches user data directly using the ORM (request.user).
    """
    # The user object is directly available via request.user thanks to login_required
    user = request.user

    # You can add more data to the context if your user model has extra fields
    context = {
        "user": user,
        # Example: 'user_role': user.role,
        # Example: 'is_marked': user.is_marked,
    }
    return render(
        request, "quiz_frontend/profile.html", context
    )  # Render the profile.html template


@login_required
def attempt_list_view(request):
    """
    View to display a list of all quiz attempts made by the authenticated user.
    Fetches attempts directly using the ORM.
    """
    # Fetch attempts related to the current user
    user_attempts = QuizAttempt.objects.filter(user=request.user).order_by(
        "-submission_time"
    )  # Order by most recent

    context = {
        "attempts": user_attempts,
    }
    return render(
        request, "quiz_frontend/attempt_list.html", context
    )  # Render the attempt_list.html template


@login_required
def attempt_detail_view(request, pk):
    """
    View to display the detailed results of a specific quiz attempt.
    Fetches the attempt and its answers directly using the ORM.
    Requires the attempt's primary key (pk) from the URL.
    """
    # Fetch the specific attempt, ensure it belongs to the logged-in user
    # get_object_or_404 will raise a 404 if the attempt doesn't exist or doesn't belong to the user
    attempt = get_object_or_404(QuizAttempt, pk=pk, user=request.user)

    # Fetch the participant answers related to this attempt
    participant_answers = attempt.participant_answers.select_related(
        "question"
    ).prefetch_related("selected_options")

    # You need the quiz object to determine if correct answers should be shown
    quiz = attempt.quiz
    print(attempt.score)
    show_correct_answers = False  # Default is not to show

    # Check if correct answers should be shown based on quiz availability
    now = timezone.now()
    # --- Corrected Check if correct answers should be shown ---
    # Show correct answers if:
    # 1. The attempt is marked (quiz.is_marked is True), OR
    # 2. The quiz has an end time set AND that end time is in the past (quiz.available_to is not None AND quiz.available_to < now), OR
    # 3. The quiz has no end time set (quiz.available_to is None) - considering it 'finished' for results display.
    if (
        request.user.is_marked
        or (quiz.available_to is not None and quiz.available_to < now)
        or (quiz.available_to is None)
    ):
        show_correct_answers = True
    # --- End Corrected Check ---
    context = {
        "attempt": attempt,
        "participant_answers": participant_answers,
        "show_correct_answers": show_correct_answers,
        # You might need QuestionTypes Enum in template for logic based on question type
        "QuestionTypes": QuestionTypes,
    }
    return render(
        request, "quiz_frontend/attempt_detail.html", context
    )  # Render the attempt_detail.html template


# Add views for other features in Part 2 (Quiz Detail/Taking) here later
# --- New View (Part 2 Feature) ---


@login_required
def quiz_detail_view(request, pk):
    """
    View to display a specific quiz for the user to take.
    """
    quiz = get_object_or_404(
        Quiz.objects.prefetch_related("questions__answer_options"), pk=pk
    )

    now = timezone.now()

    # Availability check
    is_available_by_dates = (
        quiz.available_from is not None
        and quiz.available_to is not None
        and quiz.available_from <= now
        and now <= quiz.available_to
    )
    is_available_by_default = quiz.available_from is None and quiz.available_to is None

    if not (is_available_by_dates or is_available_by_default):
        return redirect(reverse("quiz_list"))

    # Get or create an attempt object (we still need this for the attempt ID,
    # though the submission API might create a new one if it's the first submission)
    # You might need to adjust this logic based on your backend's exact handling
    # of getting/creating attempts via the quiz submission endpoint.

    # Pass data to the template context
    context = {
        "quiz": quiz,
        "QuestionTypes": QuestionTypes,
        # FIX: Use 'quiz-submit' as the URL name, passing the quiz's primary key
        # Assumes 'quiz-submit' is a detail route on the QuizViewSet, e.g., /quizzes/{pk}/submit/
        "backend_api_url": request.build_absolute_uri(
            reverse("quiz-submit", kwargs={"pk": quiz.pk})
        ),
    }
    return render(request, "quiz_frontend/quiz_detail.html", context)
