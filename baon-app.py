import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta

# --- 1. APP CONFIGURATION ---
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
        history_df = pd.DataFrame(columns=['Meal_Name', 'Date_Cooked'])
    
    pantry = pantry_df.dropna(subset=['Ingredient']).set_index('Ingredient')['Amount'].to_dict()
except Exception as e:
    st.error(f"Sheet Error: {e}")
    st.stop()

# --- 3. COOLDOWN LOGIC (5 Days) ---
history_df['Date_Cooked'] = pd.to_datetime(history_df['Date_Cooked'])
recent_meals = history_df[history_df['Date_Cooked'] > (datetime.now() - timedelta(days=5))]['Meal_Name'].unique()

def get_sort_score(row):
    if row['Meal_Name'] in recent_meals: return 0
    return 2 if str(row.get('Favorite')).upper() == 'TRUE' else 1

recipes_df['Sort_Score'] = recipes_df.apply(get_sort_score, axis=1)
sorted_recipes = recipes_df.sort_values(by='Sort_Score', ascending=False)

# --- 4. MAIN UI ---
st.title("🍱 Pinoy Baon Master")
picky_mode = st.toggle("Picky Eater Mode", value=True)

for index, row in sorted_recipes.iterrows():
    if picky_mode and not row['Picky_Friendly']: continue
    
    # Check Ingredients String
    raw_ingredients = str(row['Ingredients_List'])
    
    # MANUAL SPLIT LOGIC: We replace common separators with a standard pipe |
    # then split it into a clean list
    clean_text = raw_ingredients.replace(";", ",").replace("\n", ",")
    items = [i.strip() for i in clean_text.split(",") if i.strip()]

    # Check if we can cook it
    can_cook = True
    for item in items:
        if ":" in item:
            name, qty = item.split(":")
            if pantry.get(name.strip(), 0) < int(qty.strip()):
                can_cook = False

    if can_cook:
        is_fav = str(row.get('Favorite')).upper() == 'TRUE'
        is_recent = row['Meal_Name'] in recent_meals
        
        # UI Labels
        label = f"⏳ {row['Meal_Name']}" if is_recent else (f"⭐ {row['Meal_Name']}" if is_fav else row['Meal_Name'])

        with st.expander(label):
            # Favorite Toggle
            if st.checkbox("Mark as Favorite", value=is_fav, key=f"f{index}") != is_fav:
                recipes_df.at[index, 'Favorite'] = not is_fav
                conn.update(spreadsheet=SHEET_URL, worksheet="Recipes", data=recipes_df.drop(columns=['Sort_Score']))
                st.rerun()

            st.write("**Ingredients Required:**")
            
            # --- THE "FORCE-BREAK" DISPLAY ---
            # This loop prints each item one by one. 
            # In Streamlit, calling st.write multiple times GUARANTEES separate lines.
            for single_item in items:
                st.write(f"• {single_item}")
            
            st.divider()
            
            if st.button(f"Cook {row['Meal_Name']}", key=f"b{index}"):
                for item in items:
                    name, qty = item.split(":")
                    pantry[name.strip()] -= int(qty.strip())
                
                # Update History & Pantry
                new_log = pd.DataFrame([[row['Meal_Name'], datetime.now()]], columns=['Meal_Name', 'Date_Cooked'])
                updated_history = pd.concat([history_df, new_log])
                conn.update(spreadsheet=SHEET_URL, worksheet="Pantry", data=pd.DataFrame(list(pantry.items()), columns=['Ingredient', 'Amount']))
                conn.update(spreadsheet=SHEET_URL, worksheet="History", data=updated_history)
                st.balloons()
                st.rerun()

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("🏠 Pantry Stock")
    for item, qty in pantry.items():
        st.write(f"{item}: {qty}")
