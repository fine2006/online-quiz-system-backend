# quiz_app/tests/test_user.py

import pytest
from rest_framework import status
from django.urls import reverse, NoReverseMatch
# Fixtures from conftest.py (like authenticated_client, student_user) are automatically available


# Manual Test 3: View User Details
@pytest.mark.django_db
@pytest.mark.student  # Authenticate as a student
def test_retrieve_user_details_student(authenticated_client):
    """Test that an authenticated student can retrieve their own user details."""
    try:
        user_details_url = reverse("rest_user_details")  # Ensure this URL name exists
    except NoReverseMatch:
        pytest.fail(
            "URL name 'rest_user_details' not found. Ensure your dj-rest-auth user details URL is named 'rest_user_details'."
        )

    response = authenticated_client.get(user_details_url)

    assert response.status_code == status.HTTP_200_OK, (
        f"Failed to retrieve user details. Response: {response.json()}"
    )
    response_data = response.json()

    # Assert basic user details match the authenticated user from the fixture
    # authenticated_client.user was stored in the fixture
    assert response_data["id"] == authenticated_client.user.id
    assert response_data["username"] == authenticated_client.user.username
    assert response_data["email"] == authenticated_client.user.email
    assert response_data["role"] == authenticated_client.user.role
    assert response_data["is_marked"] == authenticated_client.user.is_marked


# You could add tests for other user roles viewing their details,
# or admin viewing other users details if that endpoint exists.
