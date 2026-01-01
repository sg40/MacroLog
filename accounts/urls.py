from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("meal_log/<str:person_name>/", views.meal_log, name="meal_log"),
    path("meal_log/<str:person_name>/calculate/", views.calculate_servings, name="calculate_servings"),
]


