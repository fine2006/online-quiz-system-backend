# quiz_app/tests/conftest.py

import pytest
from rest_framework.test import APIClient
from django.urls import reverse, NoReverseMatch
from rest_framework import status

# Import necessary models, Enums, and timezone
from quiz_app.models import (
    CustomUser,
    Roles,
    Quiz,
    Question,
    AnswerOption,
    QuizAttempt,
    ParticipantAnswer,
    QuestionTypes,
)
from django.utils import timezone

# Import itertools for counter to generate unique usernames/emails
import itertools

# Use a counter to generate unique usernames/emails within the fixture's scope
user_counter = itertools.count()


@pytest.fixture
def api_client():
    """A Django REST framework APIClient instance."""
    return APIClient()


@pytest.fixture
def create_user(django_user_model):
    """A fixture to easily create different types of users with unique names/emails."""

    def _create_user(
        username=None,
        password="password123",
        role=Roles.STUDENT,
        is_marked=False,
        email=None,
    ):
        count = next(user_counter)  # Get a unique number for this creation call

        if username is None:
            username = f"testuser_{count}"  # Generate unique username

        if email is None:
            email = f"{username}_{count}@test.com"  # Generate unique email

        user = django_user_model.objects.create_user(
            username=username,
            password=password,
            email=email,
            role=role,
            is_marked=is_marked,
            # You might need to add other required fields here if your CustomUser model has them
        )
        user.is_active = True
        user.save()
        return user

    return _create_user


@pytest.fixture
def student_user(create_user):
    """A fixture for a non-marked student user with a unique name/email."""
    # Call create_user, let it generate username/email
    return create_user(role=Roles.STUDENT, is_marked=False)


@pytest.fixture
def marked_student_user(create_user):
    """A fixture for a marked student user with a unique name/email."""
    return create_user(role=Roles.STUDENT, is_marked=True)


@pytest.fixture
def teacher_user(create_user):
    """A fixture for a teacher user with a unique name/email."""
    return create_user(role=Roles.TEACHER)


@pytest.fixture
def admin_user(create_user):
    """A fixture for an admin user with a unique name/email."""
    return create_user(role=Roles.ADMIN)


@pytest.fixture
@pytest.mark.django_db
def authenticated_client(api_client, create_user, request):
    """
    A fixture that provides an authenticated APIClient.
    Uses markers like @pytest.mark.student, @pytest.mark.teacher, etc.
    The user created is determined by the marker on the test function.
    """
    user = None
    if "admin" in request.keywords:
        user = create_user(role=Roles.ADMIN)
    elif "teacher" in request.keywords:
        user = create_user(role=Roles.TEACHER)
    elif "marked_student" in request.keywords:
        user = create_user(role=Roles.STUDENT, is_marked=True)
    # Default to student if no specific user marker is provided
    elif "student" in request.keywords or not any(
        m in request.keywords for m in ["admin", "teacher", "marked_student"]
    ):
        user = create_user(role=Roles.STUDENT, is_marked=False)

    if user is None:
        pytest.fail(
            "Authenticated client fixture failed to create a user based on markers."
        )

    try:
        login_url = reverse("rest_login")
    except NoReverseMatch:
        pytest.fail(
            "URL name 'rest_login' not found. Ensure your dj-rest-auth login URL is named 'rest_login'."
        )

    login_data = {"email": user.email, "password": "password123"}

    response = api_client.post(login_url, login_data)

    assert response.status_code == status.HTTP_200_OK, (
        f"Login failed for user {user.username} ({user.role}) with email {user.email}. Response: {response.json()}"
    )
    response_json = response.json()
    assert "access" in response_json

    token = response_json["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    api_client.user = user  # Store the user object

    return api_client


@pytest.fixture
@pytest.mark.django_db
def quiz_with_questions_fixture(
    teacher_user,
):  # Requires a teacher user to assign as owner
    """Fixture to create a sample quiz with questions and options."""
    quiz = Quiz.objects.create(
        teacher=teacher_user,
        title="Sample Quiz for Tests",
        timing_minutes=30,
        available_from=timezone.now() - timezone.timedelta(days=1),
        available_to=timezone.now() + timezone.timedelta(days=1),
    )

    q1 = Question.objects.create(
        quiz=quiz,
        question_type=QuestionTypes.SINGLE_MCQ,
        text="What is the capital of France?",
        points=2.0,
    )
    AnswerOption.objects.create(question=q1, text="Berlin", is_correct=False)
    AnswerOption.objects.create(question=q1, text="Paris", is_correct=True)
    AnswerOption.objects.create(question=q1, text="Madrid", is_correct=False)

    q2 = Question.objects.create(
        quiz=quiz,
        question_type=QuestionTypes.TRUE_FALSE,
        text="The Earth is flat.",
        points=1.0,
        correct_answer_bool=False,
    )

    q3 = Question.objects.create(
        quiz=quiz,
        question_type=QuestionTypes.MULTI_MCQ,
        text="Which are programming languages?",
        points=3.0,
    )
    AnswerOption.objects.create(question=q3, text="Python", is_correct=True)
    AnswerOption.objects.create(question=q3, text="English", is_correct=False)
    AnswerOption.objects.create(question=q3, text="JavaScript", is_correct=True)
    AnswerOption.objects.create(question=q3, text="HTML", is_correct=False)

    return quiz


# Fixture to create a quiz and a completed attempt for testing results viewing
@pytest.fixture
@pytest.mark.django_db  # Ensure DB access for this fixture
# FIX: Change dependency from student_user to authenticated_client
def completed_attempt_fixture(
    authenticated_client, quiz_with_questions_fixture
):  # Requires authenticated_client and a quiz
    """Fixture to create a quiz and a completed attempt for it."""
    quiz = quiz_with_questions_fixture  # Use the quiz fixture
    # FIX: Use the user from the authenticated_client fixture
    user = authenticated_client.user

    # Get the questions and their correct answers (using pk instead of text is more robust)
    q1 = quiz.questions.get(question_type=QuestionTypes.SINGLE_MCQ)
    q2 = quiz.questions.get(question_type=QuestionTypes.TRUE_FALSE)
    q3 = quiz.questions.get(question_type=QuestionTypes.MULTI_MCQ)

    q1_correct_option = q1.answer_options.get(text="Paris")
    q3_correct_options = list(q3.answer_options.filter(is_correct=True))

    # Create an attempt where some answers are correct, some are wrong
    # Associate the attempt with the user from the authenticated_client
    attempt = QuizAttempt.objects.create(user=user, quiz=quiz)

    # Answer Question 1 (MCQ) - Correct
    pa1 = ParticipantAnswer.objects.create(
        attempt=attempt,
        question=q1,
        selected_answer_bool=None,
    )
    pa1.selected_options.set([q1_correct_option])

    # Answer Question 2 (True/False) - Wrong (select True when correct is False)
    pa2 = ParticipantAnswer.objects.create(
        attempt=attempt,
        question=q2,
        selected_answer_bool=True,
    )
    # pa2.selected_options.set([]) # Redundant for empty ManyToMany

    # Answer Question 3 (Multi-MCQ) - Partially Correct (select Python but miss JavaScript)
    q3_python_option = q3.answer_options.get(text="Python")
    pa3 = ParticipantAnswer.objects.create(
        attempt=attempt,
        question=q3,
        selected_answer_bool=None,
    )
    pa3.selected_options.set([q3_python_option])

    # Recalculate correctness and score after creating answers
    pa1.determine_correctness()
    pa2.determine_correctness()
    pa3.determine_correctness()

    attempt.calculate_score()

    return attempt
