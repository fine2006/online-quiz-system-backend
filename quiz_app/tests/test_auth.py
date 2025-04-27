# quiz_app/tests/test_auth.py

import pytest
from rest_framework import status
from django.urls import reverse, NoReverseMatch
# Fixtures from conftest.py (like api_client, student_user) are automatically available


# Manual Test 1: Login as Student
@pytest.mark.django_db
@pytest.mark.student  # Use the student_user fixture via marker (optional here but good practice)
def test_student_login(api_client, student_user):
    """Test that a student user can log in successfully."""
    try:
        login_url = reverse("rest_login")  # Ensure your login URL is named 'rest_login'
    except NoReverseMatch:
        pytest.fail(
            "URL name 'rest_login' not found. Ensure your dj-rest-auth login URL is named 'rest_login'."
        )

    login_data = {"email": student_user.email, "password": "password123"}

    response = api_client.post(login_url, login_data)

    assert response.status_code == status.HTTP_200_OK, (
        f"Login failed. Response: {response.json()}"
    )
    response_json = response.json()
    assert "access" in response_json
    # If refresh tokens are enabled, you might also check for it
    # assert 'refresh' in response_json


# Manual Test 2: Token Refresh (Requires refresh token to be enabled and obtained)
# This test assumes your dj-rest-auth setup provides refresh tokens
# @pytest.mark.skip(reason="Token refresh test requires refresh token config and setup")
@pytest.mark.django_db
def test_token_refresh(api_client, student_user):
    """Test that an access token can be refreshed using a refresh token."""
    try:
        login_url = reverse("rest_login")
        refresh_url = reverse("token_refresh")  # Ensure this URL name exists
    except NoReverseMatch as e:
        pytest.fail(
            f"URL name not found: {e}. Ensure your dj-rest-auth URLs are named correctly."
        )

    # First, log in to get tokens
    login_data = {"email": student_user.email, "password": "password123"}
    login_response = api_client.post(login_url, login_data)
    assert login_response.status_code == status.HTTP_200_OK
    login_json = login_response.json()
    assert "refresh" in login_json  # Assert refresh token is present
    refresh_token = login_json["refresh"]

    # Now, use the refresh token to get a new access token
    refresh_data = {"refresh": refresh_token}
    refresh_response = api_client.post(refresh_url, refresh_data)

    assert refresh_response.status_code == status.HTTP_200_OK, (
        f"Token refresh failed. Response: {refresh_response.json()}"
    )
    refresh_json = refresh_response.json()
    assert "access" in refresh_json  # Assert new access token is present
    # Optionally check if the new access token is different from the old one
    # assert refresh_json['access'] != login_json['access']
