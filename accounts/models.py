from django.db import models

from foods.models import Food


class Person(models.Model):
    """
    A household member whose meals/macros are being planned.
    
    There is a single Django admin user (your mom) who manages these people.
    Each Person record stores that member's baseline daily macro targets.
    """

    name = models.CharField(max_length=100, unique=True)
    notes = models.TextField(
        blank=True,
        help_text="Optional notes about this person (preferences, restrictions, etc.).",
    )

    # Core daily macro targets
    protein_grams = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Target grams of protein per day.",
    )
    carbs_grams = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Target grams of carbohydrates per day.",
    )
    fats_grams = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Target grams of fat per day.",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck if this person is no longer being tracked.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class DailyMacroLog(models.Model):
    """
    A snapshot of one person's macro plan and actual portions for a single day.
    
    This is the core "macro log" you described: it ties together the date,
    the person's requirements for that day, and (later) the meals/portions.
    """

    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="daily_logs",
    )
    date = models.DateField()

    # Store the *planned* macro requirements for that day.
    # These are copied from Person at the time the day is planned,
    # so that if their baseline changes later, old days stay accurate.
    required_protein_grams = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Target grams of protein for this day.",
    )
    required_carbs_grams = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Target grams of carbohydrates for this day.",
    )
    required_fats_grams = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Target grams of fat for this day.",
    )

    # Optionally, you can track the *actual* totals after calculation.
    actual_protein_grams = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Total grams of protein actually planned for this day.",
    )
    actual_carbs_grams = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Total grams of carbohydrates actually planned for this day.",
    )
    actual_fats_grams = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Total grams of fat actually planned for this day.",
    )

    notes = models.TextField(
        blank=True,
        help_text="Any notes about this day (training day, sick, special event, etc.).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "person__name"]
        unique_together = ("person", "date")

    def __str__(self) -> str:
        return f"{self.person.name} - {self.date}"


class MealEntry(models.Model):
    """
    A single food portion within a specific meal slot (breakfast/lunch/dinner/etc.)
    for a given person's DailyMacroLog.

    Multiple MealEntry rows with the same (daily_log, meal_type) together form
    the full meal and can contain multiple different foods.
    """

    MEAL_TYPE_CHOICES = [
        ("breakfast", "Breakfast"),
        ("lunch", "Lunch"),
        ("dinner", "Dinner"),
        ("snack", "Snack"),
        ("other", "Other"),
    ]

    daily_log = models.ForeignKey(
        DailyMacroLog,
        on_delete=models.CASCADE,
        related_name="meal_entries",
    )
    meal_type = models.CharField(
        max_length=20,
        choices=MEAL_TYPE_CHOICES,
        default="other",
    )
    food = models.ForeignKey(
        Food,
        on_delete=models.PROTECT,
        related_name="meal_entries",
    )
    servings = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text="How many servings of this food (e.g. 1.5).",
    )

    # Optional: store pre-calculated macros at the time of planning.
    # This makes historical data stable even if the Food entry is later edited.
    protein_grams = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total grams of protein from this entry (optional cache).",
    )
    carbs_grams = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total grams of carbohydrates from this entry (optional cache).",
    )
    fats_grams = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total grams of fat from this entry (optional cache).",
    )

    notes = models.TextField(
        blank=True,
        help_text="Optional notes for this entry (e.g. adjustments, brand detail).",
    )

    class Meta:
        ordering = ["daily_log__date", "meal_type", "id"]

    def __str__(self) -> str:
        return f"{self.daily_log.person.name} - {self.daily_log.date} - {self.meal_type} - {self.food.name} x {self.servings}"

