import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import time

# --- 1. APP CONFIG ---
st.set_page_config(page_title="Pinoy Baon Master", page_icon="🍱")

# --- 2. CONNECTION ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    # ttl=0 is mandatory to see changes after st.rerun()
    p_df = conn.read(worksheet="Pantry", ttl=0)
    r_df = conn.read(worksheet="Recipes", ttl=0)
    try:
        h_df = conn.read(worksheet="History", ttl=0)
    except:
        h_df = pd.DataFrame(columns=['Meal_Name', 'Date_Cooked'])
    return p_df, r_df, h_df

pantry_df, recipes_df, history_df = load_data()

# Clean dataframes
pantry_df = pantry_df.dropna(subset=['Ingredient'])
pantry = pantry_df.set_index('Ingredient')['Amount'].to_dict()

# --- 3. SORTING LOGIC ---
# Force Date_Cooked to string to prevent format mismatch errors
history_df['Date_Cooked'] = history_df['Date_Cooked'].astype(str)
today_str = datetime.now().strftime("%Y-%m-%d")
five_days_ago = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

# Find recent meals (String comparison works for YYYY-MM-DD)
recent_meals = history_df[history_df['Date_Cooked'] > five_days_ago]['Meal_Name'].unique()

def get_score(row):
    if row['Meal_Name'] in recent_meals: return 0
    is_fav = str(row.get('Favorite', 'FALSE')).upper() == 'TRUE'
    return 2 if is_fav else 1

recipes_df['Sort_Score'] = recipes_df.apply(get_score, axis=1)
sorted_recipes = recipes_df.sort_values(by='Sort_Score', ascending=False)

# --- 4. MAIN UI ---
st.title("🍱 Pinoy Baon Master")
picky_mode = st.toggle("Picky Eater Mode", value=True)

for index, row in sorted_recipes.iterrows():
    if picky_mode and str(row.get('Picky_Friendly', 'FALSE')).upper() != 'TRUE':
        continue
    
    # Inline ingredients display
    raw_ing = str(row['Ingredients_List'])
    items = [i.strip() for i in raw_ing.split(",")]

    # Availability Check
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
            
            if st.button(f"Cook {row['Meal_Name']}", key=f"c_{index}"):
                # 1. Deduct locally
                for itm in items:
                    if ":" in itm:
                        n, q = itm.split(":")
                        pantry[n.strip()] = int(pantry[n.strip()]) - int(q.strip())
                
                # 2. Add to History locally (Strictly as Strings)
                new_entry = pd.DataFrame({
                    'Meal_Name': [str(row['Meal_Name'])], 
                    'Date_Cooked': [today_str]
                })
                
                # Combine and drop any completely empty rows
                new_history_df = pd.concat([history_df.dropna(how='all'), new_entry], ignore_index=True)
                new_pantry_df = pd.DataFrame(list(pantry.items()), columns=['Ingredient', 'Amount'])

                # 3. PUSH TO GOOGLE SHEETS
                try:
                    # Explicitly update both sheets
                    conn.update(worksheet="Pantry", data=new_pantry_df)
                    conn.update(worksheet="History", data=new_history_df)
                    
                    st.success(f"Deducted ingredients & logged {row['Meal_Name']}!")
                    st.balloons()
                    time.sleep(1) # Give Google time to sync
                    st.rerun()
                except Exception as e:
                    st.error(f"Sync failed: {e}")

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("🏠 Pantry")
    st.dataframe(pd.DataFrame(list(pantry.items()), columns=['Item', 'Qty']), hide_index=True)
    
    st.header("📜 History")
    if not history_df.empty:
        st.write(history_df.tail(5))
