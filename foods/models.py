from django.db import models


class Food(models.Model):
    """
    A basic food item OR a labeled recipe with known macros.
    
    Macros are stored per 100 g by default so it is easy to scale portions,
    but you can also set a "default serving size" (like 1 slice, 1 cup, etc.).
    """

    name = models.CharField(max_length=200, unique=True)

    # Optional grouping/labels
    brand = models.CharField(
        max_length=100,
        blank=True,
        help_text="Brand or source (optional).",
    )
    category = models.CharField(
        max_length=100,
        blank=True,
        help_text="Category like 'protein', 'carb', 'fat', 'recipe', 'snack', etc.",
    )
    is_recipe = models.BooleanField(
        default=False,
        help_text="Check if this is a multi-ingredient recipe rather than a single ingredient.",
    )

    # Macro information per *serving*
    # (a serving can be whatever makes sense: 1 slice, 1 cup, 1 cookie, etc.)
    protein_g_per_serving = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        help_text="Protein (g) per serving.",
    )
    carbs_g_per_serving = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        help_text="Carbohydrates (g) per serving.",
    )
    fats_g_per_serving = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        help_text="Fat (g) per serving.",
    )

    # Serving description to make UI friendlier (e.g. 1 slice, 1 cup, 1 cookie)
    serving_name = models.CharField(
        max_length=100,
        blank=True,
        help_text='e.g. "1 slice", "1 cup", "1 cookie" (optional).',
    )

    notes = models.TextField(
        blank=True,
        help_text="Any notes about this food (e.g. special handling, recipe details).",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to hide this food from future planning while keeping history.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
