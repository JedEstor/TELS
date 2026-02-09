from django.urls import path, include
from . import views
from .api import api
from django.contrib import admin

#app_name = "app"

urlpatterns = [
    #path('home/', views.home, name='home')
    path("", views.customer_list, name="customer_list"), 
    path("customers/tep/<int:tep_id>/", views.customer_detail, name="customer_detail"),
    path("api/", api.urls),
    path("admin/", admin.site.urls),
]
