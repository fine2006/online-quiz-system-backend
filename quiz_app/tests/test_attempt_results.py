# quiz_app/tests/test_attempt_results.py

import pytest
from rest_framework import status
from django.urls import reverse, NoReverseMatch
# Fixtures from conftest.py (like authenticated_client, completed_attempt_fixture) are automatically available


# Manual Test 7: List User's Quiz Attempts
@pytest.mark.django_db
@pytest.mark.student  # Authenticate as a student
def test_list_attempts_student(authenticated_client, completed_attempt_fixture):
    """Test that an authenticated student can list their own quiz attempts."""
    # Use the completed_attempt_fixture to ensure at least one attempt exists
    # This fixture also creates the quiz and user, associated with this attempt.

    try:
        # FIX: Change basename to 'attempt' to match router registration
        list_url = reverse("attempt-list")  # Ensure this URL name exists
    except NoReverseMatch:
        # Update the error message to reflect the correct expected basename
        pytest.fail(
            "URL name 'attempt-list' not found. Ensure your QuizAttemptViewSet is registered with basename='attempt'."
        )

    response = authenticated_client.get(list_url)

    assert response.status_code == status.HTTP_200_OK, (
        f"Failed to list attempts as student. Response: {response.json()}"
    )
    response_data = response.json()

    # Assert pagination structure
    assert isinstance(response_data, dict)
    assert "count" in response_data
    assert "next" in response_data
    assert "previous" in response_data
    assert "results" in response_data
    assert isinstance(response_data["results"], list)

    # Assert that the list contains at least one attempt (the one from the fixture)
    assert len(response_data["results"]) >= 1

    # Optional: Check that the user field in the results matches the authenticated user
    for attempt_data in response_data["results"]:
        assert "user" in attempt_data
        assert attempt_data["user"]["id"] == authenticated_client.user.id

    # Optional: Check some fields in the listed attempts, e.g., the score
    found_fixture_attempt = False
    for attempt_data in response_data["results"]:
        # Note: Attempt ID from the fixture might not be the first in the list if order_by is different
        if attempt_data.get("id") == completed_attempt_fixture.id:
            assert attempt_data.get("score") == completed_attempt_fixture.score
            found_fixture_attempt = True
            break
    assert found_fixture_attempt, (
        f"Attempt from fixture (ID {completed_attempt_fixture.id}) not found in list."
    )


# Manual Test 8: Retrieve Specific Quiz Attempt Results
@pytest.mark.django_db
@pytest.mark.student  # Authenticate as a student
def test_retrieve_attempt_results_student(
    authenticated_client, completed_attempt_fixture
):
    """Test that an authenticated student can retrieve their own specific attempt results."""
    attempt = completed_attempt_fixture  # Use the fixture to ensure a completed attempt exists

    try:
        # FIX: Change basename to 'attempt' to match router registration
        retrieve_url = reverse(
            "attempt-detail", kwargs={"pk": attempt.pk}
        )  # Ensure this URL name exists
    except NoReverseMatch:
        # Update the error message to reflect the correct expected basename
        pytest.fail(
            "URL name 'attempt-detail' not found. Ensure your QuizAttemptViewSet is registered with basename='attempt'."
        )

    response = authenticated_client.get(retrieve_url)

    assert response.status_code == status.HTTP_200_OK, (
        f"Failed to retrieve attempt results. Response: {response.json()}"
    )
    response_data = response.json()

    # Assert basic attempt details match the fixture object
    assert response_data["id"] == attempt.pk
    assert response_data["score"] == attempt.score
    assert response_data["user"]["id"] == authenticated_client.user.id
    assert response_data["quiz"]["id"] == attempt.quiz.pk

    # Assert participant answers are included and have expected fields
    assert "participant_answers" in response_data
    assert isinstance(response_data["participant_answers"], list)
    assert (
        len(response_data["participant_answers"]) == attempt.participant_answers.count()
    )

    # Check details of a sample participant answer
    if response_data["participant_answers"]:
        sample_pa_data = response_data["participant_answers"][0]  # Get the first one

        assert "question" in sample_pa_data
        assert (
            "selected_options" in sample_pa_data
            or "selected_answer_bool" in sample_pa_data
        )
        assert "is_correct" in sample_pa_data

        # Check conditional display of correct answers based on quiz availability
        # completed_attempt_fixture sets available_to in the future (+1 day)
        # So, correct answers should be visible in the results.
        sample_pa_question_type = sample_pa_data.get("question", {}).get(
            "question_type"
        )

        # Ensure QuestionTypes is accessible (it should be from conftest imports)
        from quiz_app.models import QuestionTypes

        if sample_pa_question_type == QuestionTypes.TRUE_FALSE.value:
            assert "correct_answer_bool" in sample_pa_data
        elif sample_pa_question_type in [
            QuestionTypes.SINGLE_MCQ.value,
            QuestionTypes.MULTI_MCQ.value,
        ]:
            assert "correct_options" in sample_pa_data


# You could add tests for a different student attempting to view this attempt (should fail with 403)
# or for a Teacher/Admin viewing this attempt (should pass).
