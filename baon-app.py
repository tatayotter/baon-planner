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
    pantry_df = conn.read(spreadsheet=SHEET_URL, worksheet="Pantry", ttl=0)
    recipes_df = conn.read(spreadsheet=SHEET_URL, worksheet="Recipes", ttl=0)
    
    try:
        history_df = conn.read(spreadsheet=SHEET_URL, worksheet="History", ttl=0)
    except:
        # Create empty history if tab is missing or new
        history_df = pd.DataFrame(columns=['Meal_Name', 'Date_Cooked'])

    pantry = pantry_df.dropna(subset=['Ingredient']).set_index('Ingredient')['Amount'].to_dict()
except Exception as e:
    st.error(f"Connection Error: {e}")
    st.stop()

# --- 3. SORTING LOGIC (Cooldown & Favorites) ---
history_df['Date_Cooked'] = pd.to_datetime(history_df['Date_Cooked'])
five_days_ago = datetime.now() - timedelta(days=5)

# Identify meals cooked within the last 5 days
recent_meals = history_df[history_df['Date_Cooked'] > five_days_ago]['Meal_Name'].unique()

def get_sort_score(row):
    # Score 0: Cooked within 5 days (ALWAYS Bottom)
    if row['Meal_Name'] in recent_meals:
        return 0
    # Score 2: Favorite & Not Recent (Top)
    is_fav = str(row.get('Favorite', 'FALSE')).upper() == 'TRUE'
    if is_fav:
        return 2
    # Score 1: Normal & Not Recent (Middle)
    return 1

recipes_df['Sort_Score'] = recipes_df.apply(get_sort_score, axis=1)
sorted_recipes = recipes_df.sort_values(by='Sort_Score', ascending=False)

# --- 4. MAIN UI ---
st.title("🍱 Pinoy Baon Master")
picky_mode = st.toggle("Picky Eater Mode (Kids Only)", value=True)

st.subheader("🍳 Available Meals")

for index, row in sorted_recipes.iterrows():
    # Filter for Picky Friendly
    is_picky = str(row.get('Picky_Friendly', 'FALSE')).upper() == 'TRUE'
    if picky_mode and not is_picky:
        continue
    
    # Process Ingredients
    raw_ingreds = str(row['Ingredients_List'])
    ingredient_items = [i.strip() for i in raw_ingreds.split(",")]

    # Check if we have enough stock
    can_cook = True
    for item in ingredient_items:
        if ":" in item:
            name, qty = item.split(":")
            if pantry.get(name.strip(), 0) < int(qty.strip()):
                can_cook = False

    if can_cook:
        is_fav = str(row.get('Favorite', 'FALSE')).upper() == 'TRUE'
        is_recent = row['Meal_Name'] in recent_meals
        
        # Labeling with Icons
        if is_recent:
            label = f"⏳ {row['Meal_Name']} (Cooldown)"
        elif is_fav:
            label = f"⭐ {row['Meal_Name']}"
        else:
            label = row['Meal_Name']

        with st.expander(label):
            # Favorite Checkbox (Syncs to Column D)
            new_fav = st.checkbox("Favorite ⭐", value=is_fav, key=f"f_{index}")
            if new_fav != is_fav:
                recipes_df.at[index, 'Favorite'] = new_fav
                conn.update(spreadsheet=SHEET_URL, worksheet="Recipes", data=recipes_df.drop(columns=['Sort_Score']))
                st.rerun()

            st.write(f"**Ingredients:** {raw_ingreds}")
            
            if st.button(f"Cook {row['Meal_Name']}", key=f"b_{index}"):
                # 1. Deduct from Pantry
                for item in ingredient_items:
                    if ":" in item:
                        n, q = item.split(":")
                        pantry[n.strip()] -= int(q.strip())
                
                # 2. Update History
                new_entry = pd.DataFrame([[row['Meal_Name'], datetime.now().strftime("%Y-%m-%d")]], 
                                       columns=['Meal_Name', 'Date_Cooked'])
                updated_history = pd.concat([history_df, new_entry], ignore_index=True)
                
                # 3. Batch Update Google Sheets
                conn.update(spreadsheet=SHEET_URL, worksheet="Pantry", data=pd.DataFrame(list(pantry.items()), columns=['Ingredient', 'Amount']))
                conn.update(spreadsheet=SHEET_URL, worksheet="History", data=updated_history)
                
                st.balloons()
                st.rerun()

# --- 5. SIDEBAR: PANTRY & HISTORY ---
with st.sidebar:
    # Tab 1: Inventory
    st.header("🏠 Pantry Inventory")
    for item, qty in pantry.items():
        st.write(f"**{item}**: {qty}")
    
    st.divider()
    
    # Tab 2: Cooking History
    st.header("📜 Cooking History")
    if not history_df.empty:
        # Sort history to show most recent at the top
        display_history = history_df.sort_values(by='Date_Cooked', ascending=False).head(10)
        st.dataframe(display_history, use_container_width=True, hide_index=True)
    else:
        st.write("No meals logged yet.")
