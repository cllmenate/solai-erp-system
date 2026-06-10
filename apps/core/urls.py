from django.urls import path

from apps.core import views

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("signup/", views.signup_trial_view, name="signup_trial"),
    path("signup-success/", views.signup_success_view, name="signup_success"),
    path("set-password/<str:token>/", views.set_password_view, name="set_password"),
    path("recovery/", views.password_recovery_request_view, name="password_recovery"),
    path("recovery/confirm/<str:token>/", views.password_recovery_confirm_view, name="password_recovery_confirm"),
    path("invite/create/", views.invite_create_view, name="invite_create"),
    path("invite/accept/<str:token>/", views.invite_accept_view, name="invite_accept"),
    path("settings/profile/", views.profile_view, name="settings_profile"),
    path("settings/roles/", views.role_list_view, name="settings_roles"),
    path("settings/roles/create/", views.role_create_view, name="settings_role_create"),
    path("settings/roles/<int:pk>/edit/", views.role_edit_view, name="settings_role_edit"),
    path("settings/roles/<int:pk>/toggle-active/", views.role_toggle_active_view, name="settings_role_toggle_active"),
    path("settings/roles/<int:pk>/permissions/", views.role_permissions_view, name="settings_role_permissions"),
    path("settings/users/", views.user_list_view, name="settings_users"),
    path("settings/users/create/", views.user_create_view, name="settings_role_user_create"),
    path("settings/users/<uuid:pk>/edit/", views.user_edit_view, name="settings_user_edit"),
    path("settings/users/<uuid:pk>/toggle-active/", views.user_toggle_active_view, name="settings_user_toggle_active"),
]
