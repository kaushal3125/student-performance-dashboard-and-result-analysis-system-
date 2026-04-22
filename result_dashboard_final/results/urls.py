from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('upload/', views.upload_csv, name='upload'),
    path('report/', views.export_pdf, name='report'),
    path('export-csv/', views.export_csv, name='export_csv'),
    path('download-sample/', views.download_sample, name='download_sample'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
]
