import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import time

# -------------------------------------------------
# 1. APP CONFIG
# -------------------------------------------------
st.set_page_config(
    page_title="Pinoy Baon Master",
    page_icon="🍱",
    layout="centered"
)

conn = st.connection("gsheets", type=GSheetsConnection)

# -------------------------------------------------
# 2. DATA LOADING & CLEANING
# -------------------------------------------------
@st.cache_data(ttl=0)
def load_data():
    pantry = conn.read("Pantry")
    recipes = conn.read("Recipes")

    try:
        history = conn.read("History")
    except Exception:
        history = pd.DataFrame(columns=["Meal_Name", "Date_Cooked"])

    return pantry, recipes, history


pantry_df, recipes_df, history_df = load_data()

# Pantry → clean + numeric
pantry_df = pantry_df.dropna(subset=["Ingredient"])
pantry_df["Amount"] = pd.to_numeric(pantry_df["Amount"], errors="coerce").fillna(0).astype(int)
pantry = pantry_df.set_index("Ingredient")["Amount"].to_dict()

# History → datetime
history_df["Date_Cooked"] = pd.to_datetime(history_df["Date_Cooked"], errors="coerce")

# -------------------------------------------------
# 3. HELPERS
# -------------------------------------------------
def parse_ingredients(raw: str) -> dict:
    """
    'Chicken:1, Garlic:2' → {'Chicken': 1, 'Garlic': 2}
    """
    items = {}
    for part in str(raw).split(","):
        if ":" in part:
            name, qty = part.split(":", 1)
            items[name.strip()] = int(float(qty.strip()))
    return items


def can_cook(recipe_items: dict, pantry: dict) -> bool:
    return all(pantry.get(item, 0) >= qty for item, qty in recipe_items.items())


def cook_recipe(recipe_items: dict, pantry: dict) -> dict:
    updated = pantry.copy()
    for item, qty in recipe_items.items():
        updated[item] -= qty
    return updated


# -------------------------------------------------
# 4. COOLDOWN + SORTING
# -------------------------------------------------
cooldown_cutoff = datetime.now() - timedelta(days=5)
recent_meals = set(
    history_df.loc[history_df["Date_Cooked"] > cooldown_cutoff, "Meal_Name"]
)


def recipe_score(row):
    if row["Meal_Name"] in recent_meals:
        return 0
    return 2 if str(row.get("Favorite", "")).upper() == "TRUE" else 1


recipes_df["Sort_Score"] = recipes_df.apply(recipe_score, axis=1)
recipes_df = recipes_df.sort_values("Sort_Score", ascending=False)

# -------------------------------------------------
# 5. UI
# -------------------------------------------------
st.title("🍱 Pinoy Baon Master")
picky_mode = st.toggle("Picky Eater Mode (Kids)", value=True)

for idx, row in recipes_df.iterrows():
    if picky_mode and str(row.get("Picky_Friendly", "")).upper() != "TRUE":
        continue

    ingredients = parse_ingredients(row["Ingredients_List"])

    if not can_cook(ingredients, pantry):
        continue

    is_recent = row["Meal_Name"] in recent_meals
    is_fav = str(row.get("Favorite", "")).upper() == "TRUE"

    icon = "⏳" if is_recent else ("⭐" if is_fav else "🍲")

    with st.expander(f"{icon} {row['Meal_Name']}"):
        st.write("**Ingredients:**", row["Ingredients_List"])

        if st.button(f"Confirm: Cook {row['Meal_Name']}", key=f"cook_{idx}"):
            pantry = cook_recipe(ingredients, pantry)

            history_df = pd.concat(
                [
                    history_df,
                    pd.DataFrame(
                        {
                            "Meal_Name": [row["Meal_Name"]],
                            "Date_Cooked": [datetime.now()],
                        }
                    ),
                ],
                ignore_index=True,
            )

            conn.update(
                "Pantry",
                pd.DataFrame(
                    pantry.items(), columns=["Ingredient", "Amount"]
                ),
            )
            conn.update("History", history_df)

            st.success("Synced with Google Sheets!")
            st.balloons()
            time.sleep(1)
            st.rerun()

# -------------------------------------------------
# 6. SIDEBAR
# -------------------------------------------------
with st.sidebar:
    st.header("🏠 Pantry Inventory")
    st.dataframe(
        pd.DataFrame(pantry.items(), columns=["Item", "Qty"]),
        hide_index=True,
    )

    st.divider()

    st.header("📜 Last 5 Meals")
    if history_df.empty:
        st.info("No meals cooked yet.")
    else:
        st.table(
            history_df.sort_values("Date_Cooked", ascending=False).head(5)
        )
