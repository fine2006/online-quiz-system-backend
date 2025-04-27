# quiz_app/tests/test_quiz_submission.py

import pytest
from rest_framework import status
from django.urls import reverse, NoReverseMatch
# Fixtures from conftest.py (like authenticated_client, quiz_with_questions_fixture) are automatically available


# Manual Test 6: Submit Quiz Attempt
@pytest.mark.django_db
@pytest.mark.student  # Authenticate as a student
def test_submit_quiz_attempt_student(authenticated_client, quiz_with_questions_fixture):
    """Test that an authenticated student can submit a quiz attempt."""
    quiz = quiz_with_questions_fixture  # Use the fixture to ensure a quiz with questions exists

    try:
        submit_url = reverse(
            "quiz-submit", kwargs={"pk": quiz.pk}
        )  # Ensure 'quiz-submit' URL name exists for the @action
    except NoReverseMatch:
        pytest.fail(
            "URL name 'quiz-submit' not found. Ensure your @action(detail=True, url_path='submit', name='submit') is set up with a basename='quiz'."
        )

    # Construct a sample submission payload based on the quiz_with_questions_fixture
    # This assumes you know the structure and question/option IDs from the fixture
    # Get question objects from the created quiz
    q1 = quiz.questions.get(
        text="What is the capital of France?"
    )  # SINGLE_MCQ, Paris is correct
    q2 = quiz.questions.get(text="The Earth is flat.")  # TRUE_FALSE, False is correct
    q3 = quiz.questions.get(
        text="Which are programming languages?"
    )  # MULTI_MCQ, Python/JavaScript are correct

    # Get correct option IDs for Q1 and Q3 from the created quiz object
    q1_correct_option_id = q1.answer_options.get(text="Paris").id
    q3_correct_option_ids = list(
        q3.answer_options.filter(is_correct=True).values_list("id", flat=True)
    )  # Python and JavaScript

    # Create a payload with some correct and some incorrect answers
    submission_payload = {
        "quiz_id": quiz.pk,
        "answers": [
            {
                "question_id": q1.pk,
                "selected_option_ids": [q1_correct_option_id],  # Correct answer for Q1
                "selected_answer_bool": None,
            },
            {
                "question_id": q2.pk,
                "selected_option_ids": [],
                "selected_answer_bool": True,  # Incorrect answer for Q2
            },
            {
                "question_id": q3.pk,
                "selected_option_ids": q3_correct_option_ids,  # Correct answer for Q3
                "selected_answer_bool": None,
            },
        ],
    }

    response = authenticated_client.post(submit_url, submission_payload, format="json")

    # Assert the status code is 201 Created
    assert response.status_code == status.HTTP_201_CREATED, (
        f"Failed to submit quiz attempt. Response: {response.json()}"
    )

    response_data = response.json()

    # Assert key fields in the response for the created attempt
    assert "id" in response_data  # Check that attempt ID is present
    assert response_data["user"]["id"] == authenticated_client.user.id
    assert response_data["quiz"]["id"] == quiz.pk
    assert "score" in response_data  # Check score is present

    # Optional: Assert the calculated score based on the payload
    # Correct for Q1 (+2.0), Incorrect for Q2 (+0.0), Correct for Q3 (+3.0)
    # Total expected score: 2.0 + 0.0 + 3.0 = 5.0
    assert response_data["score"] == 5.0

    # Optional: Assert the rank (might need other attempts in the DB for realistic rank)
    # On a fresh test database, this should be rank 1 if it's the first attempt for this quiz
    # assert response_data['rank'] == 1 # This might vary depending on test execution order


# You could add tests for submitting as a marked student (should fail),
# submitting after the window closes, submitting invalid data, etc.
