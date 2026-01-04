import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta

# --- 1. APP CONFIG ---
st.set_page_config(page_title="Pinoy Baon Master", page_icon="🍱", layout="centered")

# --- 2. DATA CONNECTION ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1DgVuak6x-AHQcltPoK8fB25T644lTUbkeiH3E3KiMYc/edit"
conn = st.connection("gsheets", type=GSheetsConnection)

# TTL=0 is critical to ensure it doesn't show "Old" data after a cook
pantry_df = conn.read(spreadsheet=SHEET_URL, worksheet="Pantry", ttl=0)
recipes_df = conn.read(spreadsheet=SHEET_URL, worksheet="Recipes", ttl=0)
try:
    history_df = conn.read(spreadsheet=SHEET_URL, worksheet="History", ttl=0)
except:
    history_df = pd.DataFrame(columns=['Meal_Name', 'Date_Cooked'])

# Process Pantry
pantry_df = pantry_df.dropna(subset=['Ingredient'])
pantry = pantry_df.set_index('Ingredient')['Amount'].to_dict()

# --- 3. COOLDOWN & SORTING ---
history_df['Date_Cooked'] = pd.to_datetime(history_df['Date_Cooked'], errors='coerce')
five_days_ago = datetime.now() - timedelta(days=5)
recent_meals = history_df[history_df['Date_Cooked'] > five_days_ago]['Meal_Name'].unique()

def get_score(row):
    if row['Meal_Name'] in recent_meals: return 0
    is_fav = str(row.get('Favorite', 'FALSE')).upper() == 'TRUE'
    return 2 if is_fav else 1

recipes_df['Sort_Order'] = recipes_df.apply(get_score, axis=1)
sorted_recipes = recipes_df.sort_values(by='Sort_Order', ascending=False)

# --- 4. MAIN UI ---
st.title("🍱 Pinoy Baon Master")
picky_mode = st.toggle("Picky Eater Mode (Kids Only)", value=True)

# Use a loop to display meals
for index, row in sorted_recipes.iterrows():
    # Filter for Picky
    if picky_mode and str(row.get('Picky_Friendly', 'FALSE')).upper() != 'TRUE':
        continue
    
    # Check Ingredients
    raw_ing = str(row['Ingredients_List'])
    ing_items = [i.strip() for i in raw_ing.split(",")]

    can_cook = True
    missing_stock = []
    for item in ing_items:
        if ":" in item:
            name, qty = item.split(":")
            # Convert to int to ensure math works
            if pantry.get(name.strip(), 0) < int(qty.strip()):
                can_cook = False
                missing_stock.append(name.strip())

    if can_cook:
        is_fav = str(row.get('Favorite', 'FALSE')).upper() == 'TRUE'
        icon = "⏳" if row['Meal_Name'] in recent_meals else ("⭐" if is_fav else "🍲")
        
        with st.expander(f"{icon} {row['Meal_Name']}"):
            st.write(f"**Ingredients:** {raw_ing}")
            
            # THE COOK BUTTON (Unique per row)
            if st.button(f"Confirm Cook: {row['Meal_Name']}", key=f"cook_{index}"):
                # 1. Deduct locally
                for item in ing_items:
                    if ":" in item:
                        n, q = item.split(":")
                        pantry[n.strip()] = int(pantry[n.strip()]) - int(q.strip())
                
                # 2. Add to History locally
                new_row = pd.DataFrame([[row['Meal_Name'], datetime.now().strftime("%Y-%m-%d")]], 
                                     columns=['Meal_Name', 'Date_Cooked'])
                new_history_df = pd.concat([history_df, new_row], ignore_index=True)
                
                # 3. Format DataFrames for Sheet
                new_pantry_df = pd.DataFrame(list(pantry.items()), columns=['Ingredient', 'Amount'])
                
                # 4. PUSH TO SHEETS
                try:
                    conn.update(spreadsheet=SHEET_URL, worksheet="Pantry", data=new_pantry_df)
                    conn.update(spreadsheet=SHEET_URL, worksheet="History", data=new_history_df)
                    st.success("Updating Sheets...")
                    st.balloons()
                    st.rerun()
                except Exception as e:
                    st.error(f"Write Error: {e}")

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("🏠 Pantry")
    st.dataframe(pd.DataFrame(list(pantry.items()), columns=['Item', 'Qty']), hide_index=True)
    
    st.header("📜 History")
    if not history_df.empty:
        st.write(history_df.sort_values(by='Date_Cooked', ascending=False).head(5))
