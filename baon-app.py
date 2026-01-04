import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta

# --- 1. APP CONFIG ---
st.set_page_config(page_title="Pinoy Baon Master", page_icon="🍱", layout="centered")

# --- 2. CONNECTION ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1DgVuak6x-AHQcltPoK8fB25T644lTUbkeiH3E3KiMYc/edit"
conn = st.connection("gsheets", type=GSheetsConnection)

# Load data with NO caching to ensure we see updates immediately
pantry_df = conn.read(spreadsheet=SHEET_URL, worksheet="Pantry", ttl=0)
recipes_df = conn.read(spreadsheet=SHEET_URL, worksheet="Recipes", ttl=0)
try:
    history_df = conn.read(spreadsheet=SHEET_URL, worksheet="History", ttl=0)
except:
    history_df = pd.DataFrame(columns=['Meal_Name', 'Date_Cooked'])

# Clean and prepare Pantry
pantry_df = pantry_df.dropna(subset=['Ingredient'])
pantry = pantry_df.set_index('Ingredient')['Amount'].to_dict()

# --- 3. COOLDOWN & SORTING ---
history_df['Date_Cooked'] = pd.to_datetime(history_df['Date_Cooked'], errors='coerce')
five_days_ago = datetime.now() - timedelta(days=5)
recent_meals = history_df[history_df['Date_Cooked'] > five_days_ago]['Meal_Name'].unique()

def get_score(row):
    if row['Meal_Name'] in recent_meals: return 0
    return 2 if str(row.get('Favorite', 'FALSE')).upper() == 'TRUE' else 1

recipes_df['Sort_Order'] = recipes_df.apply(get_score, axis=1)
sorted_recipes = recipes_df.sort_values(by='Sort_Order', ascending=False)

# --- 4. MAIN UI ---
st.title("🍱 Pinoy Baon Master")
picky_mode = st.toggle("Picky Eater Mode (Kids Only)", value=True)

for index, row in sorted_recipes.iterrows():
    # Picky Filter
    is_picky = str(row.get('Picky_Friendly', 'FALSE')).upper() == 'TRUE'
    if picky_mode and not is_picky: continue
    
    # Process ingredients
    raw_ingreds = str(row['Ingredients_List'])
    items = [i.strip() for i in raw_ingreds.split(",")]

    # Stock Check
    can_cook = True
    for itm in items:
        if ":" in itm:
            name, qty = itm.split(":")
            if pantry.get(name.strip(), 0) < int(qty.strip()):
                can_cook = False

    if can_cook:
        is_fav = str(row.get('Favorite', 'FALSE')).upper() == 'TRUE'
        label = f"⏳ {row['Meal_Name']}" if row['Meal_Name'] in recent_meals else (f"⭐ {row['Meal_Name']}" if is_fav else row['Meal_Name'])

        with st.expander(label):
            # Favorite Toggle
            if st.checkbox("Favorite ⭐", value=is_fav, key=f"f_{index}") != is_fav:
                recipes_df.at[index, 'Favorite'] = not is_fav
                conn.update(spreadsheet=SHEET_URL, worksheet="Recipes", data=recipes_df.drop(columns=['Sort_Order']))
                st.rerun()

            st.write(f"**Ingredients:** {raw_ingreds}")
            
            # THE COOK BUTTON
            if st.button(f"Cook {row['Meal_Name']}", key=f"btn_{index}"):
                # 1. Deduct from local dictionary
                for itm in items:
                    if ":" in itm:
                        n, q = itm.split(":")
                        pantry[n.strip()] = int(pantry.get(n.strip(), 0)) - int(q.strip())
                
                # 2. Update History
                new_entry = pd.DataFrame([[row['Meal_Name'], datetime.now().strftime("%Y-%m-%d")]], 
                                       columns=['Meal_Name', 'Date_Cooked'])
                updated_history = pd.concat([history_df, new_entry], ignore_index=True)
                
                # 3. Prepare dataframes for upload
                new_pantry_df = pd.DataFrame(list(pantry.items()), columns=['Ingredient', 'Amount'])
                
                # 4. FORCE UPDATE TO SHEETS
                st.write("🔄 Syncing with Google Sheets...")
                conn.update(spreadsheet=SHEET_URL, worksheet="Pantry", data=new_pantry_df)
                conn.update(spreadsheet=SHEET_URL, worksheet="History", data=updated_history)
                
                st.balloons()
                st.success(f"Successfully cooked {row['Meal_Name']}!")
                st.rerun()

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("🏠 Pantry Inventory")
    st.dataframe(pd.DataFrame(list(pantry.items()), columns=['Item', 'Qty']), hide_index=True)
    
    st.header("📜 Last 5 Meals")
    if not history_df.empty:
        st.write(history_df.sort_values(by='Date_Cooked', ascending=False).head(5))
