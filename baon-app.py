import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta

# --- 1. SETTINGS & APP CONFIG ---
st.set_page_config(page_title="Pinoy Baon Master", page_icon="🍱", layout="centered")

# --- 2. DATA CONNECTION ---
# Replace the URL below with your actual Google Sheet URL
SHEET_URL = "https://docs.google.com/spreadsheets/d/1DgVuak6x-AHQcltPoK8fB25T644lTUbkeiH3E3KiMYc/edit"
conn = st.connection("gsheets", type=GSheetsConnection)

def load_all_data():
    try:
        p_df = conn.read(spreadsheet=SHEET_URL, worksheet="Pantry", ttl=0)
        r_df = conn.read(spreadsheet=SHEET_URL, worksheet="Recipes", ttl=0)
        try:
            h_df = conn.read(spreadsheet=SHEET_URL, worksheet="History", ttl=0)
        except:
            h_df = pd.DataFrame(columns=['Meal_Name', 'Date_Cooked'])
        return p_df, r_df, h_df
    except Exception as e:
        st.error(f"❌ Connection Error: {e}")
        return None, None, None

pantry_df, recipes_df, history_df = load_all_data()

# Stop if data failed to load
if pantry_df is None:
    st.stop()

# --- 3. DATA PROCESSING ---
# Clean Pantry Data
pantry = pantry_df.dropna(subset=['Ingredient']).set_index('Ingredient')['Amount'].to_dict()

# Process History for Cooldown
history_df['Date_Cooked'] = pd.to_datetime(history_df['Date_Cooked'], errors='coerce')
five_days_ago = datetime.now() - timedelta(days=5)
# Filter for meals cooked in last 5 days
recent_meals = history_df[history_df['Date_Cooked'] > five_days_ago]['Meal_Name'].unique()

# --- 4. SORTING LOGIC ---
def calculate_priority(row):
    # Cooldown (Bottom - Score 0)
    if row['Meal_Name'] in recent_meals:
        return 0
    # Favorites (Top - Score 2)
    is_fav = str(row.get('Favorite', 'FALSE')).upper() == 'TRUE'
    if is_fav:
        return 2
    # Standard (Middle - Score 1)
    return 1

recipes_df['Sort_Order'] = recipes_df.apply(calculate_priority, axis=1)
sorted_recipes = recipes_df.sort_values(by='Sort_Order', ascending=False)

# --- 5. MAIN UI ---
st.title("🍱 Pinoy Baon Master")
picky_mode = st.toggle("Picky Eater Mode (Kids Only)", value=True)

st.subheader("🍳 Available Meals")

found_meal = False
for index, row in sorted_recipes.iterrows():
    # Picky Filter
    is_picky_val = str(row.get('Picky_Friendly', 'FALSE')).upper() == 'TRUE'
    if picky_mode and not is_picky_val:
        continue
    
    # Parse Ingredients
    raw_ingreds = str(row['Ingredients_List'])
    ing_items = [i.strip() for i in raw_ingreds.split(",")]

    # Check Stock Availability
    has_enough = True
    for item in ing_items:
        if ":" in item:
            name, qty = item.split(":")
            if pantry.get(name.strip(), 0) < int(qty.strip()):
                has_enough = False

    if has_enough:
        found_meal = True
        is_fav_val = str(row.get('Favorite', 'FALSE')).upper() == 'TRUE'
        
        # Determine Label Icon
        if row['Meal_Name'] in recent_meals:
            label = f"⏳ {row['Meal_Name']} (Cooldown)"
        elif is_fav_val:
            label = f"⭐ {row['Meal_Name']}"
        else:
            label = row['Meal_Name']

        with st.expander(label):
            # Favorite Checkbox
            fav_check = st.checkbox("Favorite this meal", value=is_fav_val, key=f"f_{index}")
            if fav_check != is_fav_val:
                recipes_df.at[index, 'Favorite'] = fav_check
                conn.update(spreadsheet=SHEET_URL, worksheet="Recipes", data=recipes_df.drop(columns=['Sort_Order']))
                st.success("Favorite status updated!")
                st.rerun()

            st.write(f"**Ingredients (Inline):** {raw_ingreds}")
            
            if st.button(f"Cook {row['Meal_Name']}", key=f"btn_{index}"):
                try:
                    # 1. Update Pantry Stock
                    for item in ing_items:
                        if ":" in item:
                            n, q = item.split(":")
                            pantry[n.strip()] -= int(q.strip())
                    
                    # 2. Add to History
                    new_h = pd.DataFrame([[row['Meal_Name'], datetime.now().strftime("%Y-%m-%d")]], 
                                       columns=['Meal_Name', 'Date_Cooked'])
                    updated_history = pd.concat([history_df, new_h], ignore_index=True)
                    
                    # 3. Save to Sheets
                    conn.update(spreadsheet=SHEET_URL, worksheet="Pantry", data=pd.DataFrame(list(pantry.items()), columns=['Ingredient', 'Amount']))
                    conn.update(spreadsheet=SHEET_URL, worksheet="History", data=updated_history)
                    
                    st.balloons()
                    st.toast(f"Logged {row['Meal_Name']} to History!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Update failed: {e}")

if not found_meal:
    st.info("No meals available based on current pantry stock or filters.")

# --- 6. SIDEBAR: PANTRY & HISTORY ---
with st.sidebar:
    st.header("🏠 Pantry Inventory")
    # Using a simple table for inventory
    st.table(pd.DataFrame(list(pantry.items()), columns=['Item', 'Qty']))
    
    st.divider()
    
    st.header("📜 Cooking History")
    if not history_df.empty:
        # Show last 5 meals cooked
        recent_history = history_df.sort_values(by='Date_Cooked', ascending=False).head(5)
        st.write(recent_history[['Meal_Name', 'Date_Cooked']])
    else:
        st.write("No history recorded yet.")
