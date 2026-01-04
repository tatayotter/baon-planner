import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta

# --- 1. APP CONFIG ---
st.set_page_config(page_title="Pinoy Baon Master", page_icon="🍱", layout="centered")

# --- 2. CONNECTION ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1DgVuak6x-AHQcltPoK8fB25T644lTUbkeiH3E3KiMYc/edit"
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    p = conn.read(spreadsheet=SHEET_URL, worksheet="Pantry", ttl=0)
    r = conn.read(spreadsheet=SHEET_URL, worksheet="Recipes", ttl=0)
    try:
        h = conn.read(spreadsheet=SHEET_URL, worksheet="History", ttl=0)
    except:
        h = pd.DataFrame(columns=['Meal_Name', 'Date_Cooked'])
    return p, r, h

pantry_df, recipes_df, history_df = load_data()
pantry = pantry_df.dropna(subset=['Ingredient']).set_index('Ingredient')['Amount'].to_dict()

# --- 3. SORTING ---
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
picky_mode = st.toggle("Picky Eater Mode", value=True)

for index, row in sorted_recipes.iterrows():
    if picky_mode and not str(row.get('Picky_Friendly', 'FALSE')).upper() == 'TRUE': continue
    
    # Inline ingredients display
    raw_ing = str(row['Ingredients_List'])
    ing_items = [i.strip() for i in raw_ing.split(",")]

    # Stock Check
    can_cook = True
    for item in ing_items:
        if ":" in item:
            name, qty = item.split(":")
            if pantry.get(name.strip(), 0) < int(qty.strip()):
                can_cook = False

    if can_cook:
        is_fav = str(row.get('Favorite', 'FALSE')).upper() == 'TRUE'
        label = f"⏳ {row['Meal_Name']}" if row['Meal_Name'] in recent_meals else (f"⭐ {row['Meal_Name']}" if is_fav else row['Meal_Name'])

        with st.expander(label):
            # Favorite Toggle
            new_fav = st.checkbox("Favorite ⭐", value=is_fav, key=f"f_{index}")
            if new_fav != is_fav:
                recipes_df.at[index, 'Favorite'] = new_fav
                conn.update(spreadsheet=SHEET_URL, worksheet="Recipes", data=recipes_df.drop(columns=['Sort_Order']))
                st.rerun()

            st.write(f"**Ingredients:** {raw_ing}")
            
            if st.button(f"Cook {row['Meal_Name']}", key=f"btn_{index}"):
                with st.spinner('Updating Google Sheets...'):
                    try:
                        # 1. Update Local Pantry
                        for item in ing_items:
                            if ":" in item:
                                n, q = item.split(":")
                                pantry[n.strip()] -= int(q.strip())
                        
                        # 2. Add to History
                        new_h = pd.DataFrame([[row['Meal_Name'], datetime.now().strftime("%Y-%m-%d")]], columns=['Meal_Name', 'Date_Cooked'])
                        full_history = pd.concat([history_df, new_h], ignore_index=True)
                        
                        # 3. PUSH TO GOOGLE SHEETS
                        conn.update(spreadsheet=SHEET_URL, worksheet="Pantry", data=pd.DataFrame(list(pantry.items()), columns=['Ingredient', 'Amount']))
                        conn.update(spreadsheet=SHEET_URL, worksheet="History", data=full_history)
                        
                        st.balloons()
                        st.success("Sheet Updated Successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to update Sheet: {e}")

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("🏠 Pantry Inventory")
    st.table(pd.DataFrame(list(pantry.items()), columns=['Item', 'Qty']))
    
    st.header("📜 Recent History")
    if not history_df.empty:
        st.write(history_df.sort_values(by='Date_Cooked', ascending=False).head(5))
