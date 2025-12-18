from django.contrib import admin

from .models import DailyMacroLog, Meal, MealItem, Person


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("name", "protein_grams", "carbs_grams", "fats_grams", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "notes")


class MealItemInline(admin.TabularInline):
    model = MealItem
    extra = 1
    autocomplete_fields = ("food",)


class MealInline(admin.StackedInline):
    model = Meal
    extra = 1
    show_change_link = True


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
    inlines = [MealInline]


@admin.register(Meal)
class MealAdmin(admin.ModelAdmin):
    list_display = ("daily_log", "name", "meal_type", "order")
    list_filter = ("meal_type", "daily_log__date", "daily_log__person")
    search_fields = ("name", "notes", "daily_log__person__name")
    autocomplete_fields = ("daily_log",)
    inlines = [MealItemInline]


@admin.register(MealItem)
class MealItemAdmin(admin.ModelAdmin):
    list_display = ("meal", "food", "servings")
    list_filter = ("meal__daily_log__date", "meal__daily_log__person")
    search_fields = ("meal__name", "food__name")
    autocomplete_fields = ("meal", "food")

