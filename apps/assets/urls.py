from django.urls import path

from apps.assets import views

urlpatterns = [
    # Stock Dashboard
    path("dashboard/", views.stock_dashboard_view, name="stock_dashboard"),

    # Item CRUD
    path("items/", views.item_list_view, name="item_list"),
    path("items/create/", views.item_create_view, name="item_create"),
    path("items/<uuid:pk>/", views.item_detail_view, name="item_detail"),
    path("items/<uuid:pk>/edit/", views.item_update_view, name="item_edit"),
    path("items/<uuid:pk>/delete/", views.item_delete_view, name="item_delete"),

    # Brand CRUD
    path("brands/", views.brand_list_view, name="brand_list"),
    path("brands/create/", views.brand_create_view, name="brand_create"),
    path("brands/<uuid:pk>/edit/", views.brand_update_view, name="brand_edit"),
    path("brands/<uuid:pk>/delete/", views.brand_delete_view, name="brand_delete"),

    # Category CRUD
    path("categories/", views.category_list_view, name="category_list"),
    path("categories/create/", views.category_create_view, name="category_create"),
    path("categories/<uuid:pk>/edit/", views.category_update_view, name="category_edit"),
    path("categories/<uuid:pk>/delete/", views.category_delete_view, name="category_delete"),

    # Model CRUD
    path("models/", views.model_list_view, name="model_list"),
    path("models/create/", views.model_create_view, name="model_create"),
    path("models/<uuid:pk>/edit/", views.model_update_view, name="model_edit"),
    path("models/<uuid:pk>/delete/", views.model_delete_view, name="model_delete"),

    # Batch CRUD
    path("batches/", views.batch_list_view, name="batch_list"),
    path("batches/create/", views.batch_create_view, name="batch_create"),
    path("batches/<uuid:pk>/edit/", views.batch_update_view, name="batch_edit"),
    path("batches/<uuid:pk>/delete/", views.batch_delete_view, name="batch_delete"),
]
