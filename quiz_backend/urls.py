# project/urls.py
from django.contrib import admin
from django.urls import path, include

# Import the SocialLoginView and the Google adapter
from quiz_app.views import GoogleLoginView

urlpatterns = [
    path("admin/", admin.site.urls),
    # App URLs
    path("api/", include("quiz_app.urls")),
    # dj-rest-auth and allauth URLs
    path("api/auth/", include("dj_rest_auth.urls")),
    path("api/auth/registration/", include("dj_rest_auth.registration.urls")),
    # Include the social login URLs for Google
    # This creates the URL pattern 'api/auth/google/' that will handle the POST request with the code.
    # Required for dj-rest-auth, though allauth URLs might not be hit directly by api
    # === USE YOUR CUSTOM GOOGLE LOGIN VIEW HERE ===
    # This now uses the subclass with the adapter_class attribute set
    path("api/auth/google/", GoogleLoginView.as_view(), name="rest_google_login"),
    # ================================
    # If you use allauth views for email confirmation etc., keep this.
    # If only API, you might remove or adjust based on dj-rest-auth setup.
    path("accounts/", include("allauth.urls")),  # Needed by dj-rest-auth registration
    path("", include("quiz_frontend.urls")),
]
