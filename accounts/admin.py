from django.contrib import admin

from .models import DailyMacroLog, MealEntry, Person


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("name", "protein_grams", "carbs_grams", "fats_grams", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "notes")


class MealEntryInline(admin.TabularInline):
    model = MealEntry
    extra = 1
    autocomplete_fields = ("food",)


@admin.register(DailyMacroLog)
class DailyMacroLogAdmin(admin.ModelAdmin):
    list_display = (
        "person",
        "date",
        "required_protein_grams",
        "required_carbs_grams",
        "required_fats_grams",
    )
    list_filter = ("date", "person")
    search_fields = ("person__name", "notes")
    autocomplete_fields = ("person",)
    inlines = [MealEntryInline]


@admin.register(MealEntry)
class MealEntryAdmin(admin.ModelAdmin):
    list_display = ("daily_log", "meal_type", "food", "servings")
    list_filter = ("meal_type", "daily_log__date", "daily_log__person")
    search_fields = ("food__name", "daily_log__person__name")
    autocomplete_fields = ("daily_log", "food")

