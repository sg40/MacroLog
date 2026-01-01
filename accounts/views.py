import json
from decimal import Decimal

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from foods.models import Food
from .models import Person

try:
    from scipy.optimize import minimize
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


def home(request):
    """
    Very simple home page: list all people and their daily macro requirements.
    """
    people = Person.objects.all().order_by("name")
    return render(request, "accounts/home.html", {"people": people})


def meal_log(request, person_name):
    """
    Meal logging page for a specific person.
    Shows interactive food selection for Breakfast, Lunch, and Dinner.
    """
    person = get_object_or_404(Person, name__iexact=person_name)
    foods = Food.objects.filter(is_active=True).order_by("name")
    return render(request, "accounts/meal_log.html", {"person": person, "foods": foods})


@csrf_exempt
@require_http_methods(["POST"])
def calculate_servings(request, person_name):
    """
    Calculate optimal servings for selected foods to meet macro goals.
    Uses optimization to balance macros across meals and allows supplementation.
    """
    if not SCIPY_AVAILABLE:
        return JsonResponse({"error": "scipy is required for serving calculations. Install it with: pip install scipy"})

    person = get_object_or_404(Person, name__iexact=person_name)
    
    # Check if person has macro targets
    if not person.protein_grams or not person.carbs_grams or not person.fats_grams:
        return JsonResponse({"error": "Person must have protein, carbs, and fats targets set."})

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data"})

    # Get or create protein powder and heavy cream
    protein_powder, _ = Food.objects.get_or_create(
        name="Protein Powder",
        defaults={
            "category": "protein",
            "protein_g_per_serving": Decimal("25.0"),
            "carbs_g_per_serving": Decimal("3.0"),
            "fats_g_per_serving": Decimal("1.0"),
            "serving_name": "1 scoop",
            "is_recipe": False,
        }
    )
    
    heavy_cream, _ = Food.objects.get_or_create(
        name="Heavy Cream",
        defaults={
            "category": "fat",
            "protein_g_per_serving": Decimal("1.0"),
            "carbs_g_per_serving": Decimal("1.0"),
            "fats_g_per_serving": Decimal("11.0"),
            "serving_name": "1 oz (about 2 tbsp)",
            "is_recipe": False,
        }
    )

    # Collect all foods for each meal
    meal_foods = {
        "breakfast": [],
        "lunch": [],
        "dinner": [],
    }

    for meal_type in ["breakfast", "lunch", "dinner"]:
        food_ids = data.get(meal_type, [])
        for food_id in food_ids:
            try:
                food = Food.objects.get(id=food_id, is_active=True)
                meal_foods[meal_type].append(food)
            except Food.DoesNotExist:
                continue

    # Build optimization problem
    all_foods = []
    meal_indices = {"breakfast": [], "lunch": [], "dinner": []}
    
    for meal_type in ["breakfast", "lunch", "dinner"]:
        for food in meal_foods[meal_type]:
            idx = len(all_foods)
            all_foods.append(food)
            meal_indices[meal_type].append(idx)

    # Add protein powder and heavy cream as optional supplements
    protein_powder_idx = len(all_foods)
    all_foods.append(protein_powder)
    heavy_cream_idx = len(all_foods)
    all_foods.append(heavy_cream)

    if len(all_foods) == 2:  # Only supplements
        return JsonResponse({"error": "Please select at least one food for at least one meal."})

    # Target macros
    target_protein = float(person.protein_grams)
    target_carbs = float(person.carbs_grams)
    target_fats = float(person.fats_grams)

    # Objective: minimize variance of macros across meals (balance meals) + penalize supplement use
    def objective(servings):
        # Calculate total macros per meal
        meal_totals = {"breakfast": [0, 0, 0], "lunch": [0, 0, 0], "dinner": [0, 0, 0]}
        
        for meal_type in ["breakfast", "lunch", "dinner"]:
            for idx in meal_indices[meal_type]:
                food = all_foods[idx]
                s = servings[idx]
                meal_totals[meal_type][0] += s * float(food.protein_g_per_serving)
                meal_totals[meal_type][1] += s * float(food.carbs_g_per_serving)
                meal_totals[meal_type][2] += s * float(food.fats_g_per_serving)
        
        # Add supplements to all meals equally
        protein_powder_servings = servings[protein_powder_idx] / 3.0
        heavy_cream_servings = servings[heavy_cream_idx] / 3.0
        
        for meal_type in ["breakfast", "lunch", "dinner"]:
            meal_totals[meal_type][0] += protein_powder_servings * float(protein_powder.protein_g_per_serving)
            meal_totals[meal_type][1] += protein_powder_servings * float(protein_powder.carbs_g_per_serving)
            meal_totals[meal_type][2] += protein_powder_servings * float(protein_powder.fats_g_per_serving)
            meal_totals[meal_type][0] += heavy_cream_servings * float(heavy_cream.protein_g_per_serving)
            meal_totals[meal_type][1] += heavy_cream_servings * float(heavy_cream.carbs_g_per_serving)
            meal_totals[meal_type][2] += heavy_cream_servings * float(heavy_cream.fats_g_per_serving)
        
        # Calculate variance of total macros across meals
        total_macros_per_meal = [sum(meal_totals[m]) for m in ["breakfast", "lunch", "dinner"]]
        mean = sum(total_macros_per_meal) / 3.0
        variance = sum((x - mean) ** 2 for x in total_macros_per_meal) / 3.0
        
        # Penalize supplement use - this ensures supplements are only used when necessary
        # Large penalty (1000) to strongly discourage supplement use unless needed
        supplement_penalty = 1000.0 * (servings[protein_powder_idx] + servings[heavy_cream_idx])
        
        return variance + supplement_penalty

    # Constraints: protein and fats must equal targets exactly, carbs must be <= target (keto limit)
    def constraint_protein(servings):
        total = 0.0
        for i, food in enumerate(all_foods):
            total += servings[i] * float(food.protein_g_per_serving)
        return total - target_protein

    def constraint_carbs_max(servings):
        # Carbs must be <= target (keto limit - can be 0, but not more than target)
        total = 0.0
        for i, food in enumerate(all_foods):
            total += servings[i] * float(food.carbs_g_per_serving)
        return target_carbs - total  # >= 0 means total <= target

    def constraint_fats(servings):
        total = 0.0
        for i, food in enumerate(all_foods):
            total += servings[i] * float(food.fats_g_per_serving)
        return total - target_fats

    # Initial guess: start with small servings
    x0 = [0.5] * len(all_foods)

    # Bounds: servings must be >= 0
    bounds = [(0, None)] * len(all_foods)

    # Constraints
    # Protein and fats must be exact (eq), carbs must be <= target (keto limit)
    constraints = [
        {"type": "eq", "fun": constraint_protein},
        {"type": "ineq", "fun": constraint_carbs_max},  # total_carbs <= target_carbs (keto limit)
        {"type": "eq", "fun": constraint_fats},
    ]

    # Solve
    try:
        result = minimize(
            objective,
            x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 1000},
        )

        if not result.success:
            return JsonResponse({"error": f"Optimization failed: {result.message}"})

        # Format results with macro calculations
        results = {
            "breakfast": [],
            "lunch": [],
            "dinner": [],
            "supplements": [],
            "daily_totals": {"protein": 0.0, "carbs": 0.0, "fats": 0.0},
            "daily_goals": {"protein": target_protein, "carbs": target_carbs, "fats": target_fats},
        }

        # Calculate per-meal totals and food contributions
        meal_totals = {"breakfast": [0.0, 0.0, 0.0], "lunch": [0.0, 0.0, 0.0], "dinner": [0.0, 0.0, 0.0]}

        for meal_type in ["breakfast", "lunch", "dinner"]:
            for idx in meal_indices[meal_type]:
                servings = result.x[idx]
                if servings > 0.001:  # Only show if significant
                    food = all_foods[idx]
                    protein = float(servings) * float(food.protein_g_per_serving)
                    carbs = float(servings) * float(food.carbs_g_per_serving)
                    fats = float(servings) * float(food.fats_g_per_serving)
                    
                    meal_totals[meal_type][0] += protein
                    meal_totals[meal_type][1] += carbs
                    meal_totals[meal_type][2] += fats
                    
                    results[meal_type].append({
                        "food_id": food.id,
                        "food_name": food.name,
                        "servings": float(servings),
                        "serving_name": food.serving_name or "serving",
                        "protein": protein,
                        "carbs": carbs,
                        "fats": fats,
                    })

        # Add supplements to meal totals
        protein_powder_servings = result.x[protein_powder_idx]
        heavy_cream_servings = result.x[heavy_cream_idx]
        
        protein_powder_per_meal = protein_powder_servings / 3.0
        heavy_cream_per_meal = heavy_cream_servings / 3.0

        if protein_powder_servings > 0.001:
            protein_pp = float(protein_powder_per_meal) * float(protein_powder.protein_g_per_serving)
            carbs_pp = float(protein_powder_per_meal) * float(protein_powder.carbs_g_per_serving)
            fats_pp = float(protein_powder_per_meal) * float(protein_powder.fats_g_per_serving)
            
            for meal_type in ["breakfast", "lunch", "dinner"]:
                meal_totals[meal_type][0] += protein_pp
                meal_totals[meal_type][1] += carbs_pp
                meal_totals[meal_type][2] += fats_pp
            
            results["supplements"].append({
                "name": "Protein Powder",
                "servings": float(protein_powder_servings),
                "serving_name": protein_powder.serving_name or "serving",
                "protein": float(protein_powder_servings) * float(protein_powder.protein_g_per_serving),
                "carbs": float(protein_powder_servings) * float(protein_powder.carbs_g_per_serving),
                "fats": float(protein_powder_servings) * float(protein_powder.fats_g_per_serving),
            })

        if heavy_cream_servings > 0.001:
            protein_hc = float(heavy_cream_per_meal) * float(heavy_cream.protein_g_per_serving)
            carbs_hc = float(heavy_cream_per_meal) * float(heavy_cream.carbs_g_per_serving)
            fats_hc = float(heavy_cream_per_meal) * float(heavy_cream.fats_g_per_serving)
            
            for meal_type in ["breakfast", "lunch", "dinner"]:
                meal_totals[meal_type][0] += protein_hc
                meal_totals[meal_type][1] += carbs_hc
                meal_totals[meal_type][2] += fats_hc
            
            results["supplements"].append({
                "name": "Heavy Cream",
                "servings": float(heavy_cream_servings),
                "serving_name": heavy_cream.serving_name or "serving",
                "protein": float(heavy_cream_servings) * float(heavy_cream.protein_g_per_serving),
                "carbs": float(heavy_cream_servings) * float(heavy_cream.carbs_g_per_serving),
                "fats": float(heavy_cream_servings) * float(heavy_cream.fats_g_per_serving),
            })

        # Add meal totals and goals to results
        for meal_type in ["breakfast", "lunch", "dinner"]:
            results[meal_type + "_total"] = {
                "protein": meal_totals[meal_type][0],
                "carbs": meal_totals[meal_type][1],
                "fats": meal_totals[meal_type][2],
            }
            results[meal_type + "_goal"] = {
                "protein": target_protein / 3.0,  # Ideal goal (1/3 of daily)
                "carbs": target_carbs / 3.0,
                "fats": target_fats / 3.0,
            }
            results["daily_totals"]["protein"] += meal_totals[meal_type][0]
            results["daily_totals"]["carbs"] += meal_totals[meal_type][1]
            results["daily_totals"]["fats"] += meal_totals[meal_type][2]

        return JsonResponse(results)

    except Exception as e:
        return JsonResponse({"error": f"Calculation error: {str(e)}"})


