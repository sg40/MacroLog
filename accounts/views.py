from django.shortcuts import render

from .models import Person


def home(request):
    """
    Very simple home page: list all people and their daily macro requirements.
    """
    people = Person.objects.all().order_by("name")
    return render(request, "accounts/home.html", {"people": people})


