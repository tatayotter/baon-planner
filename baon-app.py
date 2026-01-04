import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta

# --- 1. APP CONFIGURATION ---
st.set_page_config(
    page_title="Pinoy Baon Master",
    page_icon="🍱",
    layout="centered"
)

# --- 2. CONNECTION & DATA LOADING ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1DgVuak6x-AHQcltPoK8fB25T644lTUbkeiH3E3KiMYc/edit"
conn = st.connection("gsheets", type=GSheetsConnection)

try:
    pantry_df = conn.read(spreadsheet=SHEET_URL, worksheet="Pantry", ttl=0)
    recipes_df = conn.read(spreadsheet=SHEET_URL, worksheet="Recipes", ttl=0)
    
    try:
        history_df = conn.read(spreadsheet=SHEET_URL, worksheet="History", ttl=0)
    except:
        history_df = pd.DataFrame(columns=['Meal_Name', 'Date_Cooked'])

    # Clean empty rows
    pantry_df = pantry_df.dropna(subset=['Ingredient'])
    recipes_df = recipes_df.dropna(subset=['Meal_Name'])
    pantry = pantry_df.set_index('Ingredient')['Amount'].to_dict()

except Exception as e:
    st.error("⚠️ Connection Error! Please check your Google Sheet tabs.")
    st.stop()

# --- 3. SORTING LOGIC (Cooldown Wins) ---
history_df['Date_Cooked'] = pd.to_datetime(history_df['Date_Cooked'])
five_days_ago = datetime.now() - timedelta(days=5)
recent_meals = history_df[history_df['Date_Cooked'] > five_days_ago]['Meal_Name'].unique()

def get_sort_score(row):
    # If cooked in last 5 days, force to bottom (Score 0)
    if row['Meal_Name'] in recent_meals:
        return 0
    # If Favorite and NOT recently cooked (Score 2)
    is_fav = str(row.get('Favorite')).upper() == 'TRUE'
    if is_fav:
        return 2
    # Otherwise (Score 1)
    return 1

recipes_df['Sort_Score'] = recipes_df.apply(get_sort_score, axis=1)
sorted_recipes = recipes_df.sort_values(by='Sort_Score', ascending=False)

# --- 4. INGREDIENT PARSER HELPER ---
def get_ingredient_list(raw_string):
    """Robustly splits ingredients by comma, semicolon, or newline"""
    # Replace semicolons and newlines with commas to make splitting uniform
    clean_string = str(raw_string).replace(";", ",").replace("\n", ",")
    return [item.strip() for item in clean_string.split(",") if item.strip()]

def can_cook(ingredients_str):
    """Checks if pantry has enough stock"""
    try:
        items = get_ingredient_list(ingredients_str)
        for pair in items:
            name, qty = pair.split(":")
            if pantry.get(name.strip(), 0) < int(qty.strip()):
                return False
        return True
    except:
        return False

# --- 5. MAIN UI ---
st.title("🍱 Pinoy Baon Master")
picky_mode = st.toggle("Picky Eater Mode (Kids Only)", value=True)

st.subheader("🍳 Available Meals")

found_any = False
for index, row in sorted_recipes.iterrows():
    if picky_mode and not row['Picky_Friendly']:
        continue
    
    if can_cook(row['Ingredients_List']):
        found_any = True
        is_fav = str(row.get('Favorite')).upper() == 'TRUE'
        is_recent = row['Meal_Name'] in recent_meals
        
        # Labeling
        if is_recent:
            display_label = f"⏳ {row['Meal_Name']} (Cooldown)"
        elif is_fav:
            display_label = f"⭐ {row['Meal_Name']}"
        else:
            display_label = row['Meal_Name']

        with st.expander(display_label):
            # Favorite Toggle
            new_fav_state = st.checkbox("Favorite this meal", value=is_fav, key=f"fav_{index}")
            if new_fav_state != is_fav:
                recipes_df.at[index, 'Favorite'] = new_fav_state
                save_df = recipes_df.drop(columns=['Sort_Score'])
                conn.update(spreadsheet=SHEET_URL, worksheet="Recipes", data=save_df)
                st.rerun()

            st.write("**Ingredients Required:**")
            
            # --- THE VERTICAL LIST FIX ---
            items = get_ingredient_list(row['Ingredients_List'])
            for item in items:
                st.markdown(f"* {item}") # Using markdown forces new lines
            
            st.write("---")
            
            if st.button(f"Cook {row['Meal_Name']}", key=f"btn_{index}"):
                # Deducting
                for item in items:
                    name, qty = item.split(":")
                    pantry[name.strip()] -= int(qty.strip())
                
                # Update History
                new_log = pd.DataFrame([[row['Meal_Name'], datetime.now().strftime("%Y-%m-%d %H:%M:%S")]], 
                                     columns=['Meal_Name', 'Date_Cooked'])
                updated_history = pd.concat([history_df, new_log], ignore_index=True)
                
                # Update Sheet
                updated_pantry_df = pd.DataFrame(list(pantry.items()), columns=['Ingredient', 'Amount'])
                conn.update(spreadsheet=SHEET_URL, worksheet="Pantry", data=updated_pantry_df)
                conn.update(spreadsheet=SHEET_URL, worksheet="History", data=updated_history)
                
                st.balloons()
                st.rerun()

if not found_any:
    st.info("No meals available. Check pantry or uncheck Picky Mode.")

# --- 6. SIDEBAR ---
with st.sidebar:
    st.header("🏠 Pantry Stock")
    for item, qty in pantry.items():
        if qty <= 0: st.error(f"{item}: {qty}")
        elif qty < 100: st.warning(f"{item}: {qty}")
        else: st.write(f"**{item}**: {qty}")
