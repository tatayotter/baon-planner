import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta

# --- 1. APP CONFIG ---
st.set_page_config(page_title="Pinoy Baon Master", page_icon="🍱", layout="centered")

# --- 2. CONNECTION ---
# Using the connection name from your secrets: [connections.gsheets]
conn = st.connection("gsheets", type=GSheetsConnection)

# Load data with ttl=0 to ensure we don't use stale cached data
try:
    pantry_df = conn.read(worksheet="Pantry", ttl=0)
    recipes_df = conn.read(worksheet="Recipes", ttl=0)
    try:
        history_df = conn.read(worksheet="History", ttl=0)
    except:
        history_df = pd.DataFrame(columns=['Meal_Name', 'Date_Cooked'])
except Exception as e:
    st.error(f"Could not connect to Google Sheets. Check your Secrets and URL. Error: {e}")
    st.stop()

# Prepare Pantry
pantry_df = pantry_df.dropna(subset=['Ingredient'])
pantry = pantry_df.set_index('Ingredient')['Amount'].to_dict()

# --- 3. SORTING LOGIC ---
history_df['Date_Cooked'] = pd.to_datetime(history_df['Date_Cooked'], errors='coerce')
five_days_ago = datetime.now() - timedelta(days=5)
recent_meals = history_df[history_df['Date_Cooked'] > five_days_ago]['Meal_Name'].unique()

def get_score(row):
    if row['Meal_Name'] in recent_meals: return 0
    is_fav = str(row.get('Favorite', 'FALSE')).upper() == 'TRUE'
    return 2 if is_fav else 1

recipes_df['Sort_Score'] = recipes_df.apply(get_score, axis=1)
sorted_recipes = recipes_df.sort_values(by='Sort_Score', ascending=False)

# --- 4. MAIN UI ---
st.title("🍱 Pinoy Baon Master")
picky_mode = st.toggle("Picky Eater Mode (Kids Only)", value=True)

for index, row in sorted_recipes.iterrows():
    # Filter Picky
    if picky_mode and str(row.get('Picky_Friendly', 'FALSE')).upper() != 'TRUE':
        continue
    
    # Check Ingredients
    raw_ing = str(row['Ingredients_List'])
    items = [i.strip() for i in raw_ing.split(",")]

    can_cook = True
    for itm in items:
        if ":" in itm:
            name, qty = itm.split(":")
            if pantry.get(name.strip(), 0) < int(qty.strip()):
                can_cook = False

    if can_cook:
        is_fav = str(row.get('Favorite', 'FALSE')).upper() == 'TRUE'
        icon = "⏳" if row['Meal_Name'] in recent_meals else ("⭐" if is_fav else "🍲")
        
        with st.expander(f"{icon} {row['Meal_Name']}"):
            st.write(f"**Ingredients:** {raw_ing}")
            
            # --- THE COOK BUTTON ---
            if st.button(f"Cook {row['Meal_Name']}", key=f"cook_{index}"):
                # 1. Deduct from local Pantry
                for itm in items:
                    if ":" in itm:
                        n, q = itm.split(":")
                        pantry[n.strip()] = int(pantry.get(n.strip(), 0)) - int(q.strip())
                
                # 2. Add to History
                new_entry = pd.DataFrame({
                    'Meal_Name': [row['Meal_Name']], 
                    'Date_Cooked': [datetime.now().strftime("%Y-%m-%d")]
                })
                # Remove empty rows from history before adding new one
                clean_history = history_df.dropna(how='all')
                updated_history = pd.concat([clean_history, new_entry], ignore_index=True)
                
                # 3. Create Final DataFrames with HARD HEADERS
                # These MUST match your Sheet column headers exactly
                pantry_to_save = pd.DataFrame(list(pantry.items()), columns=['Ingredient', 'Amount'])
                history_to_save = updated_history[['Meal_Name', 'Date_Cooked']]

                # 4. SYNC TO GOOGLE SHEETS
                try:
                    conn.update(worksheet="Pantry", data=pantry_to_save)
                    conn.update(worksheet="History", data=history_to_save)
                    
                    st.success("Updating Google Sheets...")
                    st.balloons()
                    # Wait a moment for Google to finish writing
                    import time
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Update failed. This is usually a permission or header error: {e}")

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("🏠 Pantry")
    st.dataframe(pd.DataFrame(list(pantry.items()), columns=['Item', 'Qty']), hide_index=True)
    
    st.header("📜 History")
    if not history_df.empty:
        st.write(history_df.sort_values(by='Date_Cooked', ascending=False).head(5))
