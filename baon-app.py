import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import time

# --- 1. APP CONFIG ---
st.set_page_config(page_title="Pinoy Baon Master", page_icon="🍱", layout="centered")

# --- 2. THE CONNECTION ---
# This uses the secrets you provided earlier
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    # ttl=0 is the most important part; it forces the app to ignore old data
    p = conn.read(worksheet="Pantry", ttl=0)
    r = conn.read(worksheet="Recipes", ttl=0)
    try:
        h = conn.read(worksheet="History", ttl=0)
    except:
        h = pd.DataFrame(columns=['Meal_Name', 'Date_Cooked'])
    return p, r, h

# Initial Data Load
pantry_df, recipes_df, history_df = load_data()

# Clean and Map Pantry
pantry_df = pantry_df.dropna(subset=['Ingredient'])
pantry = pantry_df.set_index('Ingredient')['Amount'].to_dict()

# --- 3. COOLDOWN & SORTING ---
history_df['Date_Cooked'] = pd.to_datetime(history_df['Date_Cooked'], errors='coerce')
five_days_ago = datetime.now() - timedelta(days=5)
recent_meals = history_df[history_df['Date_Cooked'] > five_days_ago]['Meal_Name'].unique()

def get_score(row):
    # Cooldown (0) < Normal (1) < Favorite (2)
    if row['Meal_Name'] in recent_meals: return 0
    return 2 if str(row.get('Favorite', 'FALSE')).upper() == 'TRUE' else 1

recipes_df['Sort_Score'] = recipes_df.apply(get_score, axis=1)
sorted_recipes = recipes_df.sort_values(by='Sort_Score', ascending=False)

# --- 4. MAIN UI ---
st.title("🍱 Pinoy Baon Master")
picky_mode = st.toggle("Picky Eater Mode (Kids)", value=True)

for index, row in sorted_recipes.iterrows():
    if picky_mode and str(row.get('Picky_Friendly', 'FALSE')).upper() != 'TRUE':
        continue
    
    # Stock Check Logic
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
            
            # THE COOK BUTTON
            if st.button(f"Confirm: Cook {row['Meal_Name']}", key=f"c_{index}"):
                # 1. Update Pantry locally
                for itm in items:
                    if ":" in itm:
                        n, q = itm.split(":")
                        pantry[n.strip()] = int(pantry[n.strip()]) - int(q.strip())
                
                # 2. Add to History locally
                new_entry = pd.DataFrame({
                    'Meal_Name': [row['Meal_Name']], 
                    'Date_Cooked': [datetime.now().strftime("%Y-%m-%d")]
                })
                
                # Prepare clean DataFrames for the update
                final_pantry_df = pd.DataFrame(list(pantry.items()), columns=['Ingredient', 'Amount'])
                final_history_df = pd.concat([history_df, new_entry], ignore_index=True).dropna(how='all')

                # 3. PUSH TO GOOGLE SHEETS
                try:
                    conn.update(worksheet="Pantry", data=final_pantry_df)
                    conn.update(worksheet="History", data=final_history_df)
                    
                    st.success("Syncing with Google Sheets...")
                    st.balloons()
                    time.sleep(2) # Give the API time to breathe
                    st.rerun() # Force a full app refresh
                except Exception as e:
                    st.error(f"Write failed: {e}")

# --- 5. SIDEBAR: PANTRY & HISTORY ---
with st.sidebar:
    st.header("🏠 Pantry Inventory")
    st.dataframe(pd.DataFrame(list(pantry.items()), columns=['Item', 'Qty']), hide_index=True)
    
    st.divider()
    
    st.header("📜 Last 5 Meals")
    if not history_df.empty:
        # Show actual history sorted by date
        st.table(history_df.sort_values(by='Date_Cooked', ascending=False).head(5))
    else:
        st.info("No meals in history yet.")
