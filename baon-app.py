import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="Pinoy Baon Master", page_icon="🍱", layout="centered")

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

    pantry_df = pantry_df.dropna(subset=['Ingredient'])
    recipes_df = recipes_df.dropna(subset=['Meal_Name'])
    pantry = pantry_df.set_index('Ingredient')['Amount'].to_dict()
except Exception as e:
    st.error("⚠️ Connection Error! Check your sheet tabs.")
    st.stop()

# --- 3. SORTING LOGIC ---
history_df['Date_Cooked'] = pd.to_datetime(history_df['Date_Cooked'])
five_days_ago = datetime.now() - timedelta(days=5)
recent_meals = history_df[history_df['Date_Cooked'] > five_days_ago]['Meal_Name'].unique()

def get_sort_score(row):
    if row['Meal_Name'] in recent_meals:
        return 0  # Cooldown (Bottom)
    is_fav = str(row.get('Favorite')).upper() == 'TRUE'
    if is_fav:
        return 2  # Favorite (Top)
    return 1      # Normal (Middle)

recipes_df['Sort_Score'] = recipes_df.apply(get_sort_score, axis=1)
sorted_recipes = recipes_df.sort_values(by='Sort_Score', ascending=False)

# --- 4. HELPER FUNCTION ---
def can_cook(ingredients_str):
    try:
        for pair in ingredients_str.split(","):
            name, qty = pair.split(":")
            if pantry.get(name.strip(), 0) < int(qty.strip()):
                return False
        return True
    except: return False

# --- 5. MAIN UI (With Bullet Point Fix) ---
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
        
        label = row['Meal_Name']
        if is_recent: label = f"⏳ {label} (Cooldown)"
        elif is_fav: label = f"⭐ {label}"

        with st.expander(label):
            # Favorite Toggle
            new_fav_state = st.checkbox("Favorite this meal", value=is_fav, key=f"fav_{index}")
            if new_fav_state != is_fav:
                recipes_df.at[index, 'Favorite'] = new_fav_state
                conn.update(spreadsheet=SHEET_URL, worksheet="Recipes", data=recipes_df.drop(columns=['Sort_Score']))
                st.rerun()

            st.write("**Ingredients Required:**")
            
            # THE BULLET POINT FIX
            raw_ingredients = str(row['Ingredients_List'])
            ingredient_list = [item.strip() for item in raw_ingredients.split(",")]
            for item in ingredient_list:
                if item:
                    st.markdown(f"* {item}")
            
            st.divider() # Adds a small line between ingredients and button
            
            if st.button(f"Cook {row['Meal_Name']}", key=f"btn_{index}"):
                for item in ingredient_list:
                    name, qty = item.split(":")
                    pantry[name.strip()] -= int(qty.strip())
                
                new_log = pd.DataFrame([[row['Meal_Name'], datetime.now().strftime("%Y-%m-%d %H:%M:%S")]], 
                                     columns=['Meal_Name', 'Date_Cooked'])
                updated_history = pd.concat([history_df, new_log], ignore_index=True)
                
                updated_pantry_df = pd.DataFrame(list(pantry.items()), columns=['Ingredient', 'Amount'])
                conn.update(spreadsheet=SHEET_URL, worksheet="Pantry", data=updated_pantry_df)
                conn.update(spreadsheet=SHEET_URL, worksheet="History", data=updated_history)
                st.balloons()
                st.rerun()

# --- 6. SIDEBAR ---
with st.sidebar:
    st.header("🏠 Pantry Stock")
    for item, qty in pantry.items():
        if qty <= 0: st.error(f"{item}: {qty}")
        elif qty < 100: st.warning(f"{item}: {qty}")
        else: st.write(f"**{item}**: {qty}")
