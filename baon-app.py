import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta

# --- 1. APP CONFIG ---
st.set_page_config(page_title="Pinoy Baon Master", page_icon="🍱", layout="centered")

# --- 2. CONNECTION ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1DgVuak6x-AHQcltPoK8fB25T644lTUbkeiH3E3KiMYc/edit"
conn = st.connection("gsheets", type=GSheetsConnection)

try:
    # Read tabs
    pantry_df = conn.read(spreadsheet=SHEET_URL, worksheet="Pantry", ttl=0)
    recipes_df = conn.read(spreadsheet=SHEET_URL, worksheet="Recipes", ttl=0)
    
    # Try to read History, create if missing
    try:
        history_df = conn.read(spreadsheet=SHEET_URL, worksheet="History", ttl=0)
    except:
        history_df = pd.DataFrame(columns=['Meal_Name', 'Date_Cooked'])

    # Prepare Pantry Dict
    pantry = pantry_df.dropna(subset=['Ingredient']).set_index('Ingredient')['Amount'].to_dict()
except Exception as e:
    st.error(f"Connection Error: {e}")
    st.stop()

# --- 3. SORTING LOGIC (Cooldown & Favorites) ---
history_df['Date_Cooked'] = pd.to_datetime(history_df['Date_Cooked'])
five_days_ago = datetime.now() - timedelta(days=5)

# Find meals cooked in the last 5 days
recent_meals = history_df[history_df['Date_Cooked'] > five_days_ago]['Meal_Name'].unique()

def get_sort_score(row):
    """
    Score 0: Cooked within 5 days (Bottom)
    Score 2: Favorite & Not Recent (Top)
    Score 1: Normal & Not Recent (Middle)
    """
    if row['Meal_Name'] in recent_meals:
        return 0
    is_fav = str(row.get('Favorite', 'FALSE')).upper() == 'TRUE'
    if is_fav:
        return 2
    return 1

recipes_df['Sort_Score'] = recipes_df.apply(get_sort_score, axis=1)
sorted_recipes = recipes_df.sort_values(by='Sort_Score', ascending=False)

# --- 4. MAIN UI ---
st.title("🍱 Pinoy Baon Master")
picky_mode = st.toggle("Picky Eater Mode", value=True)

st.subheader("🍳 Available Meals")

for index, row in sorted_recipes.iterrows():
    # Picky Filter
    is_picky = str(row.get('Picky_Friendly', 'FALSE')).upper() == 'TRUE'
    if picky_mode and not is_picky:
        continue
    
    # Ingredients Logic (Inline)
    raw_ingreds = str(row['Ingredients_List'])
    ingredient_items = [i.strip() for i in raw_ingreds.split(",")]

    # Stock Check
    can_cook = True
    for item in ingredient_items:
        if ":" in item:
            name, qty = item.split(":")
            if pantry.get(name.strip(), 0) < int(qty.strip()):
                can_cook = False

    if can_cook:
        is_fav = str(row.get('Favorite', 'FALSE')).upper() == 'TRUE'
        is_recent = row['Meal_Name'] in recent_meals
        
        # Determine Label
        if is_recent:
            label = f"⏳ {row['Meal_Name']} (Recently Cooked)"
        elif is_fav:
            label = f"⭐ {row['Meal_Name']} (Favorite)"
        else:
            label = row['Meal_Name']

        with st.expander(label):
            # Favorite Toggle (Syncs to Column D)
            new_fav_val = st.checkbox("Favorite this meal", value=is_fav, key=f"f_{index}")
            if new_fav_val != is_fav:
                recipes_df.at[index, 'Favorite'] = new_fav_val
                conn.update(spreadsheet=SHEET_URL, worksheet="Recipes", data=recipes_df.drop(columns=['Sort_Score']))
                st.rerun()

            st.write(f"**Ingredients:** {raw_ingreds}")
            
            if st.button(f"Cook {row['Meal_Name']}", key=f"b_{index}"):
                # 1. Deduct Pantry
                for item in ingredient_items:
                    if ":" in item:
                        n, q = item.split(":")
                        pantry[n.strip()] -= int(q.strip())
                
                # 2. Add to History
                new_log = pd.DataFrame([[row['Meal_Name'], datetime.now().strftime("%Y-%m-%d")]], 
                                     columns=['Meal_Name', 'Date_Cooked'])
                updated_history = pd.concat([history_df, new_log], ignore_index=True)
                
                # 3. Update Sheet
                conn.update(spreadsheet=SHEET_URL, worksheet="Pantry", data=pd.DataFrame(list(pantry.items()), columns=['Ingredient', 'Amount']))
                conn.update(spreadsheet=SHEET_URL, worksheet="History", data=updated_history)
                
                st.balloons()
                st.rerun()

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("🏠 Pantry Inventory")
    for item, qty in pantry.items():
        st.write(f"{item}: {qty}")
