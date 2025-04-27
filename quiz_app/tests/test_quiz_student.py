# quiz_app/tests/test_quiz_student.py

import pytest
from rest_framework import status
from django.urls import reverse, NoReverseMatch
# Fixtures from conftest.py (like authenticated_client, quiz_with_questions_fixture) are automatically available


# Manual Test 4: List Quizzes for Student
@pytest.mark.django_db
@pytest.mark.student  # Authenticate as a student
def test_list_quizzes_student(authenticated_client):
    """Test that an authenticated student can list quizzes."""
    # We already have test_list_quizzes_allow_any, this adds authentication check.
    try:
        list_url = reverse(
            "quiz-list"
        )  # Ensure your QuizViewSet list URL name is 'quiz-list'
    except NoReverseMatch:
        pytest.fail(
            "URL name 'quiz-list' not found. Ensure your QuizViewSet is registered with basename='quiz'."
        )

    response = authenticated_client.get(list_url)

    assert response.status_code == status.HTTP_200_OK, (
        f"Failed to list quizzes as student. Response: {response.json()}"
    )
    response_data = response.json()

    # Assert pagination structure
    assert isinstance(response_data, dict)
    assert "count" in response_data
    assert "next" in response_data
    assert "previous" in response_data
    assert "results" in response_data
    assert isinstance(response_data["results"], list)

    # Optional: Check content of a quiz if one exists (e.g., using a fixture)
    # If using quiz_with_questions_fixture here, you could check that
    # is_correct is NOT in the answer_options for any listed quiz.
    # This confirms the read-only serializer is used correctly.
    # Example (assuming quiz_with_questions_fixture is used elsewhere and creates a quiz):
    # if response_data['results']:
    #      first_quiz = response_data['results'][0]
    #      assert 'questions' in first_quiz
    #      if first_quiz['questions']:
    #           first_question = first_quiz['questions'][0]
    #           assert 'answer_options' in first_question
    #           if first_question['answer_options']:
    #                first_option = first_question['answer_options'][0]
    #                assert 'is_correct' not in first_option # Key assertion for student view


# Manual Test 5: Retrieve Specific Quiz for Taking as Student
@pytest.mark.django_db
@pytest.mark.student  # Authenticate as a student
def test_retrieve_quiz_student(authenticated_client, quiz_with_questions_fixture):
    """Test that an authenticated student can retrieve a specific quiz."""
    quiz = quiz_with_questions_fixture  # Use the fixture to ensure a quiz exists

    try:
        retrieve_url = reverse(
            "quiz-detail", kwargs={"pk": quiz.pk}
        )  # Ensure 'quiz-detail' URL name exists
    except NoReverseMatch:
        pytest.fail(
            "URL name 'quiz-detail' not found. Ensure your QuizViewSet is registered with basename='quiz'."
        )

    response = authenticated_client.get(retrieve_url)

    assert response.status_code == status.HTTP_200_OK, (
        f"Failed to retrieve quiz as student. Response: {response.json()}"
    )
    response_data = response.json()

    # Assert basic quiz details
    assert response_data["id"] == quiz.pk
    assert response_data["title"] == quiz.title
    assert "questions" in response_data
    assert isinstance(response_data["questions"], list)

    # Crucial assertion: Check that 'is_correct' is NOT present in answer options
    for question_data in response_data.get("questions", []):
        for option_data in question_data.get("answer_options", []):
            assert "is_correct" not in option_data, (
                f"Student quiz view exposed 'is_correct' for option ID {option_data.get('id')}"
            )


# You could add tests for marked students attempting to view quizzes if permissions differ.
