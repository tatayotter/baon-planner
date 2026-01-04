import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta

# --- 1. APP CONFIG ---
st.set_page_config(page_title="Pinoy Baon Master", page_icon="🍱")

# --- 2. CONNECTION ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1DgVuak6x-AHQcltPoK8fB25T644lTUbkeiH3E3KiMYc/edit"
conn = st.connection("gsheets", type=GSheetsConnection)

try:
    # Load data from the three tabs
    pantry_df = conn.read(spreadsheet=SHEET_URL, worksheet="Pantry", ttl=0)
    recipes_df = conn.read(spreadsheet=SHEET_URL, worksheet="Recipes", ttl=0)
    try:
        history_df = conn.read(spreadsheet=SHEET_URL, worksheet="History", ttl=0)
    except:
        history_df = pd.DataFrame(columns=['Meal_Name', 'Date_Cooked'])
    
    # Process Pantry into a dictionary
    pantry = pantry_df.dropna(subset=['Ingredient']).set_index('Ingredient')['Amount'].to_dict()
except Exception as e:
    st.error(f"Error loading sheet: {e}")
    st.stop()

# --- 3. SORTING & COOLDOWN LOGIC ---
# Calculate the 5-day window
history_df['Date_Cooked'] = pd.to_datetime(history_df['Date_Cooked'])
five_days_ago = datetime.now() - timedelta(days=5)

# Identify meals cooked in the last 5 days
recent_meals = history_df[history_df['Date_Cooked'] > five_days_ago]['Meal_Name'].unique()

def get_sort_score(row):
    # Priority 0: Recently cooked (Bottom)
    if row['Meal_Name'] in recent_meals:
        return 0
    # Priority 2: Favorite AND not recently cooked (Top)
    is_fav = str(row.get('Favorite', 'FALSE')).upper() == 'TRUE'
    if is_fav:
        return 2
    # Priority 1: Normal and not recently cooked (Middle)
    return 1

recipes_df['Sort_Score'] = recipes_df.apply(get_sort_score, axis=1)
sorted_recipes = recipes_df.sort_values(by='Sort_Score', ascending=False)

# --- 4. MAIN UI ---
st.title("🍱 Pinoy Baon Master")
picky_mode = st.toggle("Picky Eater Mode", value=True)

st.subheader("🍳 Available Meals")

for index, row in sorted_recipes.iterrows():
    # Filter for Picky Friendly
    is_picky = str(row.get('Picky_Friendly', 'FALSE')).upper() == 'TRUE'
    if picky_mode and not is_picky:
        continue
    
    # Split ingredients by comma
    raw_ingreds = str(row['Ingredients_List'])
    ingredient_list = [i.strip() for i in raw_ingreds.split(",")]

    # Check if we have enough ingredients in the pantry
    can_cook = True
    for item in ingredient_list:
        if ":" in item:
            name, qty = item.split(":")
            if pantry.get(name.strip(), 0) < int(qty.strip()):
                can_cook = False

    if can_cook:
        is_fav = str(row.get('Favorite', 'FALSE')).upper() == 'TRUE'
        is_recent = row['Meal_Name'] in recent_meals
        
        # UI Styling: ⏳ for Cooldown, ⭐ for Favorites
        if is_recent:
            label = f"⏳ {row['Meal_Name']} (Cooldown)"
        elif is_fav:
            label = f"⭐ {row['Meal_Name']}"
        else:
            label = row['Meal_Name']

        with st.expander(label):
            # FAVORITE TOGGLE: Direct update to Google Sheet
            current_fav = st.checkbox("Favorite ⭐", value=is_fav, key=f"fav_{index}")
            if current_fav != is_fav:
                recipes_df.at[index, 'Favorite'] = current_fav
                # Save back to sheet (dropping the temporary Sort_Score column)
                conn.update(spreadsheet=SHEET_URL, worksheet="Recipes", data=recipes_df.drop(columns=['Sort_Score']))
                st.rerun()

            st.write("**Ingredients Required:**")
            # --- THE VERTICAL LIST FIX ---
            # Using a loop with st.markdown ensures a new line for every item
            for ing in ingredient_list:
                st.markdown(f"- {ing}")
            
            st.write("---")
            
            if st.button(f"Cook {row['Meal_Name']}", key=f"btn_{index}"):
                # 1. Update Pantry Stock
                for item in ingredient_list:
                    if ":" in item:
                        n, q = item.split(":")
                        pantry[n.strip()] -= int(q.strip())
                
                # 2. Add to History
                new_entry = pd.DataFrame([[row['Meal_Name'], datetime.now().strftime("%Y-%m-%d")]], 
                                       columns=['Meal_Name', 'Date_Cooked'])
                updated_history = pd.concat([history_df, new_entry], ignore_index=True)
                
                # 3. Update Google Sheets
                updated_pantry_df = pd.DataFrame(list(pantry.items()), columns=['Ingredient', 'Amount'])
                conn.update(spreadsheet=SHEET_URL, worksheet="Pantry", data=updated_pantry_df)
                conn.update(spreadsheet=SHEET_URL, worksheet="History", data=updated_history)
                
                st.balloons()
                st.rerun()

# --- 5. SIDEBAR INVENTORY ---
with st.sidebar:
    st.header("🏠 Pantry Inventory")
    for item, qty in pantry.items():
        st.write(f"{item}: {qty}")
