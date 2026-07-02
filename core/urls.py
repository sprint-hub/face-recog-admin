from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.custom_logout, name='logout'),
    path('', views.dashboard, name='index'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('clients/', views.clients_list, name='clients_list'),
    path('clients/create/', views.create_client, name='create_client'),
    path('clients/<uuid:pk>/', views.client_detail, name='client_detail'),
    path('clients/<uuid:pk>/edit/', views.edit_client, name='edit_client'),
    path('clients/<uuid:pk>/delete/', views.delete_client, name='delete_client'),
    path('clients/<uuid:pk>/fund/', views.fund_client, name='fund_client'),
    path('clients/<uuid:pk>/update-status/', views.update_client_status, name='update_client_status'),
    path('clients/<uuid:pk>/regenerate-keys/', views.regenerate_keys, name='regenerate_keys'),
    path('verifications/', views.verifications_list, name='verifications_list'),
    path('verifications/<int:pk>/', views.verification_detail, name='verification_detail'),
    path('verifications/export/csv/', views.verification_export_csv, name='verification_export_csv'),
    path('reports/', views.generate_report, name='generate_report'),
    path('api/client-stats/', views.get_client_stats, name='get_client_stats'),
    path('api/recent-activity/', views.recent_activity, name='recent_activity'),
]