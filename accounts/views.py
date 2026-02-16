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

    # Collect breakfast/lunch foods with user-set servings, and dinner foods (to be calculated)
    breakfast_foods_servings = []  # List of (food, servings) tuples
    lunch_foods_servings = []  # List of (food, servings) tuples
    dinner_food_ids = []  # List of food IDs (servings will be calculated)

    # Parse breakfast data (has food_id and servings)
    for item in data.get("breakfast", []):
        if isinstance(item, dict) and "food_id" in item and "servings" in item:
            try:
                food = Food.objects.get(id=item["food_id"], is_active=True)
                breakfast_foods_servings.append((food, float(item["servings"])))
            except (Food.DoesNotExist, ValueError, KeyError):
                continue

    # Parse lunch data (has food_id and servings)
    for item in data.get("lunch", []):
        if isinstance(item, dict) and "food_id" in item and "servings" in item:
            try:
                food = Food.objects.get(id=item["food_id"], is_active=True)
                lunch_foods_servings.append((food, float(item["servings"])))
            except (Food.DoesNotExist, ValueError, KeyError):
                continue

    # Parse dinner data (just food IDs)
    for food_id in data.get("dinner", []):
        if isinstance(food_id, int):
            try:
                dinner_food_ids.append(food_id)
            except (ValueError, TypeError):
                continue

    # Calculate consumed macros from breakfast and lunch
    consumed_protein = 0.0
    consumed_carbs = 0.0
    consumed_fats = 0.0

    for food, servings in breakfast_foods_servings + lunch_foods_servings:
        consumed_protein += float(servings) * float(food.protein_g_per_serving)
        consumed_carbs += float(servings) * float(food.carbs_g_per_serving)
        consumed_fats += float(servings) * float(food.fats_g_per_serving)

    # Calculate remaining targets for dinner
    remaining_protein = float(person.protein_grams) - consumed_protein
    remaining_carbs = float(person.carbs_grams) - consumed_carbs
    remaining_fats = float(person.fats_grams) - consumed_fats

    # Check if we need to calculate dinner
    if not dinner_food_ids:
        return JsonResponse({"error": "Please select at least one food for dinner."})

    # Get dinner foods
    dinner_foods = []
    for food_id in dinner_food_ids:
        try:
            food = Food.objects.get(id=food_id, is_active=True)
            dinner_foods.append(food)
        except Food.DoesNotExist:
            continue

    if not dinner_foods:
        return JsonResponse({"error": "No valid foods selected for dinner."})

    # Build optimization problem - only for dinner
    all_foods = dinner_foods.copy()
    dinner_indices = list(range(len(dinner_foods)))

    # Add protein powder and heavy cream as optional supplements
    protein_powder_idx = len(all_foods)
    all_foods.append(protein_powder)
    heavy_cream_idx = len(all_foods)
    all_foods.append(heavy_cream)

    if len(all_foods) == 2:  # Only supplements
        return JsonResponse({"error": "Please select at least one food for at least one meal."})

    # Target macros (remaining after breakfast and lunch)
    target_protein = remaining_protein
    target_carbs = remaining_carbs
    target_fats = remaining_fats

    # Objective: minimize supplement use (dinner is the only meal being optimized)
    def objective(servings):
        # Penalize supplement use - this ensures supplements are only used when necessary
        # Large penalty (1000) to strongly discourage supplement use unless needed
        supplement_penalty = 1000.0 * (servings[protein_powder_idx] + servings[heavy_cream_idx])
        return supplement_penalty

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
            "daily_goals": {"protein": float(person.protein_grams), "carbs": float(person.carbs_grams), "fats": float(person.fats_grams)},
        }

        # Calculate breakfast totals (user-set servings)
        breakfast_total = [0.0, 0.0, 0.0]
        for food, servings in breakfast_foods_servings:
            protein = float(servings) * float(food.protein_g_per_serving)
            carbs = float(servings) * float(food.carbs_g_per_serving)
            fats = float(servings) * float(food.fats_g_per_serving)
            
            breakfast_total[0] += protein
            breakfast_total[1] += carbs
            breakfast_total[2] += fats
            
            results["breakfast"].append({
                "food_id": food.id,
                "food_name": food.name,
                "servings": float(servings),
                "serving_name": food.serving_name or "serving",
                "protein": protein,
                "carbs": carbs,
                "fats": fats,
            })

        # Calculate lunch totals (user-set servings)
        lunch_total = [0.0, 0.0, 0.0]
        for food, servings in lunch_foods_servings:
            protein = float(servings) * float(food.protein_g_per_serving)
            carbs = float(servings) * float(food.carbs_g_per_serving)
            fats = float(servings) * float(food.fats_g_per_serving)
            
            lunch_total[0] += protein
            lunch_total[1] += carbs
            lunch_total[2] += fats
            
            results["lunch"].append({
                "food_id": food.id,
                "food_name": food.name,
                "servings": float(servings),
                "serving_name": food.serving_name or "serving",
                "protein": protein,
                "carbs": carbs,
                "fats": fats,
            })

        # Calculate dinner totals (calculated servings)
        dinner_total = [0.0, 0.0, 0.0]
        for idx in dinner_indices:
            servings = result.x[idx]
            if servings > 0.001:  # Only show if significant
                food = all_foods[idx]
                protein = float(servings) * float(food.protein_g_per_serving)
                carbs = float(servings) * float(food.carbs_g_per_serving)
                fats = float(servings) * float(food.fats_g_per_serving)
                
                dinner_total[0] += protein
                dinner_total[1] += carbs
                dinner_total[2] += fats
                
                results["dinner"].append({
                    "food_id": food.id,
                    "food_name": food.name,
                    "servings": float(servings),
                    "serving_name": food.serving_name or "serving",
                    "protein": protein,
                    "carbs": carbs,
                    "fats": fats,
                })

        # Add supplements to dinner only (if needed)
        protein_powder_servings = result.x[protein_powder_idx]
        heavy_cream_servings = result.x[heavy_cream_idx]

        if protein_powder_servings > 0.001:
            protein_pp = float(protein_powder_servings) * float(protein_powder.protein_g_per_serving)
            carbs_pp = float(protein_powder_servings) * float(protein_powder.carbs_g_per_serving)
            fats_pp = float(protein_powder_servings) * float(protein_powder.fats_g_per_serving)
            
            dinner_total[0] += protein_pp
            dinner_total[1] += carbs_pp
            dinner_total[2] += fats_pp
            
            results["supplements"].append({
                "name": "Protein Powder",
                "servings": float(protein_powder_servings),
                "serving_name": protein_powder.serving_name or "serving",
                "protein": protein_pp,
                "carbs": carbs_pp,
                "fats": fats_pp,
            })

        if heavy_cream_servings > 0.001:
            protein_hc = float(heavy_cream_servings) * float(heavy_cream.protein_g_per_serving)
            carbs_hc = float(heavy_cream_servings) * float(heavy_cream.carbs_g_per_serving)
            fats_hc = float(heavy_cream_servings) * float(heavy_cream.fats_g_per_serving)
            
            dinner_total[0] += protein_hc
            dinner_total[1] += carbs_hc
            dinner_total[2] += fats_hc
            
            results["supplements"].append({
                "name": "Heavy Cream",
                "servings": float(heavy_cream_servings),
                "serving_name": heavy_cream.serving_name or "serving",
                "protein": protein_hc,
                "carbs": carbs_hc,
                "fats": fats_hc,
            })

        # Add meal totals and goals to results
        results["breakfast_total"] = {
            "protein": breakfast_total[0],
            "carbs": breakfast_total[1],
            "fats": breakfast_total[2],
        }
        results["breakfast_goal"] = {
            "protein": float(person.protein_grams) / 3.0,
            "carbs": float(person.carbs_grams) / 3.0,
            "fats": float(person.fats_grams) / 3.0,
        }
        
        results["lunch_total"] = {
            "protein": lunch_total[0],
            "carbs": lunch_total[1],
            "fats": lunch_total[2],
        }
        results["lunch_goal"] = {
            "protein": float(person.protein_grams) / 3.0,
            "carbs": float(person.carbs_grams) / 3.0,
            "fats": float(person.fats_grams) / 3.0,
        }
        
        results["dinner_total"] = {
            "protein": dinner_total[0],
            "carbs": dinner_total[1],
            "fats": dinner_total[2],
        }
        results["dinner_goal"] = {
            "protein": remaining_protein,
            "carbs": remaining_carbs,
            "fats": remaining_fats,
        }
        
        # Calculate daily totals
        results["daily_totals"]["protein"] = breakfast_total[0] + lunch_total[0] + dinner_total[0]
        results["daily_totals"]["carbs"] = breakfast_total[1] + lunch_total[1] + dinner_total[1]
        results["daily_totals"]["fats"] = breakfast_total[2] + lunch_total[2] + dinner_total[2]

        return JsonResponse(results)

    except Exception as e:
        return JsonResponse({"error": f"Calculation error: {str(e)}"})


