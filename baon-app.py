import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import time

# -------------------------------------------------
# 1. APP CONFIG
# -------------------------------------------------
st.set_page_config(page_title="Pinoy Baon Master", page_icon="🍱", layout="centered")
conn = st.connection("gsheets", type=GSheetsConnection)

# -------------------------------------------------
# 2. LOAD DATA (ALWAYS FRESH)
# -------------------------------------------------
def load_data():
    pantry = conn.read(worksheet="Pantry", ttl=0)
    recipes = conn.read(worksheet="Recipes", ttl=0)
    try:
        history = conn.read(worksheet="History", ttl=0)
    except Exception:
        history = pd.DataFrame(columns=["Meal_Name", "Date_Cooked"])
    return pantry, recipes, history

pantry_df, recipes_df, history_df = load_data()

# Clean pantry
pantry_df = pantry_df.dropna(subset=["Ingredient"]).copy()
pantry_df["Amount"] = pd.to_numeric(pantry_df["Amount"], errors="coerce").fillna(0).astype(int)
pantry = pantry_df.set_index("Ingredient")["Amount"].to_dict()

# Clean history
history_df = history_df.copy()
history_df["Date_Cooked"] = pd.to_datetime(history_df.get("Date_Cooked"), errors="coerce")

# -------------------------------------------------
# 3. HELPERS
# -------------------------------------------------
def parse_ingredients(raw: str) -> dict:
    """'Chicken:1, Garlic:2' -> {'Chicken': 1, 'Garlic': 2}"""
    items = {}
    for part in str(raw).split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        name, qty = part.split(":", 1)
        name = name.strip()
        qty = qty.strip()
        if not name:
            continue
        try:
            items[name] = int(float(qty))
        except ValueError:
            continue
    return items

def can_cook(needed: dict, pantry: dict) -> bool:
    return all(pantry.get(item, 0) >= qty for item, qty in needed.items())

def apply_cook(needed: dict, pantry: dict) -> dict:
    updated = pantry.copy()
    for item, qty in needed.items():
        updated[item] = max(0, updated.get(item, 0) - qty)  # prevent negative
    return updated

def to_bool(val) -> bool:
    return str(val).strip().upper() == "TRUE"

# -------------------------------------------------
# 4. COOLDOWN & SORTING
# -------------------------------------------------
five_days_ago = datetime.now() - timedelta(days=5)
recent_meals = set(
    history_df.loc[history_df["Date_Cooked"] > five_days_ago, "Meal_Name"]
    .dropna()
    .astype(str)
    .unique()
)

def score(row):
    if row["Meal_Name"] in recent_meals:
        return 0
    return 2 if to_bool(row.get("Favorite", "FALSE")) else 1

recipes_df = recipes_df.copy()
recipes_df["Sort_Score"] = recipes_df.apply(score, axis=1)
sorted_recipes = recipes_df.sort_values(by="Sort_Score", ascending=False)

# -------------------------------------------------
# 5. MAIN UI
# -------------------------------------------------
st.title("🍱 Pinoy Baon Master")
picky_mode = st.toggle("Picky Eater Mode (Kids)", value=True)

for idx, row in sorted_recipes.iterrows():
    if picky_mode and not to_bool(row.get("Picky_Friendly", "FALSE")):
        continue

    meal_name = str(row["Meal_Name"])
    raw_ing = str(row.get("Ingredients_List", ""))

    needed = parse_ingredients(raw_ing)
    if not needed:
        continue

    if not can_cook(needed, pantry):
        continue

    is_recent = meal_name in recent_meals
    is_fav = to_bool(row.get("Favorite", "FALSE"))
    icon = "⏳" if is_recent else ("⭐" if is_fav else "🍲")

    with st.expander(f"{icon} {meal_name}"):
        st.write(f"**Ingredients:** {raw_ing}")

        if st.button(f"Confirm: Cook {meal_name}", key=f"cook_{idx}"):
            # Update pantry locally
            pantry = apply_cook(needed, pantry)

            # Add history entry (write as string for Sheets reliability)
            new_entry = pd.DataFrame(
                {"Meal_Name": [meal_name], "Date_Cooked": [datetime.now().strftime("%Y-%m-%d")]}
            )
            final_history_df = pd.concat([history_df, new_entry], ignore_index=True).dropna(how="all")

            # Final pantry df
            final_pantry_df = pd.DataFrame(pantry.items(), columns=["Ingredient", "Amount"])

            # Push to Google Sheets (CORRECT SIGNATURE)
            try:
                conn.update(worksheet="Pantry", data=final_pantry_df)
                conn.update(worksheet="History", data=final_history_df)

                st.success("Synced with Google Sheets!")
                st.balloons()
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Write failed: {e}")

# -------------------------------------------------
# 6. SIDEBAR
# -------------------------------------------------
with st.sidebar:
    st.header("🏠 Pantry Inventory")
    st.dataframe(pd.DataFrame(pantry.items(), columns=["Item", "Qty"]), hide_index=True)

    st.divider()
    st.header("📜 Last 5 Meals")

    # Reload fresh history for sidebar display
    try:
        sidebar_history = conn.read(worksheet="History", ttl=0)
        sidebar_history["Date_Cooked"] = pd.to_datetime(sidebar_history["Date_Cooked"], errors="coerce")
    except Exception:
        sidebar_history = pd.DataFrame(columns=["Meal_Name", "Date_Cooked"])

    if sidebar_history.empty:
        st.info("No meals in history yet.")
    else:
        st.table(sidebar_history.sort_values(by="Date_Cooked", ascending=False).head(5))
