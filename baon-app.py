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

# --- 3. COOLDOWN LOGIC ---
history_df['Date_Cooked'] = pd.to_datetime(history_df['Date_Cooked'])
five_days_ago = datetime.now() - timedelta(days=5)
recent_meals = history_df[history_df['Date_Cooked'] > five_days_ago]['Meal_Name'].unique()

def get_sort_score(row):
    if row['Meal_Name'] in recent_meals: return 0
    return 2 if str(row.get('Favorite')).upper() == 'TRUE' else 1

recipes_df['Sort_Score'] = recipes_df.apply(get_sort_score, axis=1)
sorted_recipes = recipes_df.sort_values(by='Sort_Score', ascending=False)

# --- 4. THE ROBUST PARSER ---
def parse_to_table(text):
    """Converts 'Chicken:200, Eggs:1' into a vertical Table (DataFrame)"""
    # This tries to split by comma, semicolon, or newline
    import re
    # Splits by any comma, semicolon, or vertical bar
    items = re.split(r'[;,|]', str(text))
    clean_items = [i.strip() for i in items if i.strip()]
    
    # Create two columns for a clean table look
    table_data = []
    for item in clean_items:
        if ":" in item:
            parts = item.split(":")
            table_data.append({"Item": parts[0].strip(), "Qty": parts[1].strip()})
        else:
            table_data.append({"Item": item, "Qty": "-"})
    return pd.DataFrame(table_data)

# --- 5. MAIN UI ---
st.title("🍱 Pinoy Baon Master")
picky_mode = st.toggle("Picky Eater Mode", value=True)

for index, row in sorted_recipes.iterrows():
    if picky_mode and not row['Picky_Friendly']: continue
    
    # Setup Data
    df_ingredients = parse_to_table(row['Ingredients_List'])
    
    # Basic Check for Ingredients
    can_cook = True
    for _, item_row in df_ingredients.iterrows():
        name = item_row['Item']
        qty = item_row['Qty']
        if qty.isdigit():
            if pantry.get(name, 0) < int(qty):
                can_cook = False

    if can_cook:
        is_fav = str(row.get('Favorite')).upper() == 'TRUE'
        label = f"⏳ {row['Meal_Name']}" if row['Meal_Name'] in recent_meals else (f"⭐ {row['Meal_Name']}" if is_fav else row['Meal_Name'])

        with st.expander(label):
            # Favorite Checkbox
            if st.checkbox("Mark as Favorite", value=is_fav, key=f"f{index}") != is_fav:
                recipes_df.at[index, 'Favorite'] = not is_fav
                conn.update(spreadsheet=SHEET_URL, worksheet="Recipes", data=recipes_df.drop(columns=['Sort_Score']))
                st.rerun()

            st.write("**Ingredients Required:**")
            
            # --- THE "NUCLEAR" VERTICAL FIX ---
            # Instead of text, we show a small table. This cannot stay inline.
            st.table(df_ingredients)
            
            if st.button(f"Cook {row['Meal_Name']}", key=f"b{index}"):
                for _, item_row in df_ingredients.iterrows():
                    name, qty = item_row['Item'], item_row['Qty']
                    if qty.isdigit():
                        pantry[name] -= int(qty)
                
                # Update History
                new_log = pd.DataFrame([[row['Meal_Name'], datetime.now()]], columns=['Meal_Name', 'Date_Cooked'])
                updated_history = pd.concat([history_df, new_log])
                
                # Update Sheet
                conn.update(spreadsheet=SHEET_URL, worksheet="Pantry", data=pd.DataFrame(list(pantry.items()), columns=['Ingredient', 'Amount']))
                conn.update(spreadsheet=SHEET_URL, worksheet="History", data=updated_history)
                st.balloons()
                st.rerun()

# --- 6. SIDEBAR ---
with st.sidebar:
    st.header("🏠 Pantry Stock")
    for item, qty in pantry.items():
        st.write(f"{item}: {qty}")
