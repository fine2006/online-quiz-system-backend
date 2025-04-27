# quiz_app/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth import get_user_model  # Get the active user model

# Import your custom user model and roles
from .models import CustomUser, Roles

# Get the custom user model
CustomUser = get_user_model()

# Optional: Try to unregister the default User model if it was registered by contrib.auth
# This avoids potential conflicts or duplicate 'Users' section if contrib.auth.admin is used.
# Use a try/except block in case contrib.auth.admin isn't fully loaded or User wasn't registered.
try:
    admin.site.unregister(
        CustomUser
    )  # Try unregistering based on the AUTH_USER_MODEL name
except admin.sites.NotRegistered:
    # If it's not registered, that's fine.
    pass
except Exception as e:
    # Handle other potential exceptions during unregistration attempt
    print(f"Warning: Could not unregister default User model. {e}")


class CustomUserAdmin(UserAdmin):
    """
    Custom Admin configuration for CustomUser model.
    Includes the fields from AbstractUser and our custom fields (role, is_marked).
    """

    # Add custom fields to the list of fields displayed on the user change form
    fieldsets = UserAdmin.fieldsets + ((None, {"fields": ("role", "is_marked")}),)

    # Add custom fields to the list of fields displayed on the user add form
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {"fields": ("role", "is_marked")}),
    )

    # Specify the fields to be displayed in the user list page
    list_display = (
        "username",
        "email",
        "role",
        "is_marked",
        "is_staff",
        "is_superuser",
        "is_active",
        "date_joined",
    )

    # Specify fields to use as links to the change view
    list_display_links = ("username", "email")

    # Add filters for the user list page
    list_filter = ("role", "is_marked", "is_staff", "is_superuser", "is_active")

    # Add search fields
    search_fields = ("username", "email")

    # Order by username by default
    ordering = ("username",)


# Register the CustomUser model with the custom admin class
admin.site.register(CustomUser, CustomUserAdmin)
