from django.contrib import admin

from .models import Food


@admin.register(Food)
class FoodAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "brand",
        "is_recipe",
        "serving_name",
        "protein_g_per_serving",
        "carbs_g_per_serving",
        "fats_g_per_serving",
        "is_active",
    )
    list_filter = ("is_active", "is_recipe", "category")
    search_fields = ("name", "brand", "category", "notes")
