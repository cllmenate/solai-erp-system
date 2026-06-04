from django.urls import path

from apps.commercial import views

urlpatterns = [
    path("partners/", views.partner_list_view, name="partner_list"),
    path("partners/create/", views.partner_create_view, name="partner_create"),
    path("partners/<uuid:pk>/", views.partner_detail_view, name="partner_detail"),
    path("partners/<uuid:pk>/edit/", views.partner_update_view, name="partner_edit"),
    path("partners/<uuid:pk>/delete/", views.partner_delete_view, name="partner_delete"),
    
    # HTMX Partials
    path("htmx/contact-row/", views.htmx_contact_row, name="htmx_contact_row"),
    path("htmx/address-row/", views.htmx_address_row, name="htmx_address_row"),
]
