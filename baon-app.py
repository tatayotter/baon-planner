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
    try:
        p_df = conn.read(spreadsheet=SHEET_URL, worksheet="Pantry", ttl=0)
        r_df = conn.read(spreadsheet=SHEET_URL, worksheet="Recipes", ttl=0)
        try:
            h_df = conn.read(spreadsheet=SHEET_URL, worksheet="History", ttl=0)
        except:
            h_df = pd.DataFrame(columns=['Meal_Name', 'Date_Cooked'])
        return p_df, r_df, h_df
    except Exception as e:
        st.error(f"Failed to read sheet: {e}")
        return None, None, None

pantry_df, recipes_df, history_df = load_data()

if pantry_df is not None:
    # Prepare Pantry Dict
    pantry = pantry_df.dropna(subset=['Ingredient']).set_index('Ingredient')['Amount'].to_dict()

    # --- 3. SORTING LOGIC ---
    history_df['Date_Cooked'] = pd.to_datetime(history_df['Date_Cooked'], errors='coerce')
    five_days_ago = datetime.now() - timedelta(days=5)
    recent_meals = history_df[history_df['Date_Cooked'] > five_days_ago]['Meal_Name'].unique()

    def get_sort_score(row):
        if row['Meal_Name'] in recent_meals: return 0
        is_fav = str(row.get('Favorite', 'FALSE')).upper() == 'TRUE'
        return 2 if is_fav else 1

    recipes_df['Sort_Score'] = recipes_df.apply(get_sort_score, axis=1)
    sorted_recipes = recipes_df.sort_values(by='Sort_Score', ascending=False)

    # --- 4. MAIN UI ---
    st.title("🍱 Pinoy Baon Master")
    picky_mode = st.toggle("Picky Eater Mode", value=True)

    for index, row in sorted_recipes.iterrows():
        is_picky = str(row.get('Picky_Friendly', 'FALSE')).upper() == 'TRUE'
        if picky_mode and not is_picky: continue
        
        raw_ingreds = str(row['Ingredients_List'])
        ing_list = [i.strip() for i in raw_ingreds.split(",")]

        # Labeling
        is_fav = str(row.get('Favorite', 'FALSE')).upper() == 'TRUE'
        label = f"⏳ {row['Meal_Name']}" if row['Meal_Name'] in recent_meals else (f"⭐ {row['Meal_Name']}" if is_fav else row['Meal_Name'])

        with st.expander(label):
            # Favorite Toggle
            new_fav = st.checkbox("Favorite ⭐", value=is_fav, key=f"f_{index}")
            if new_fav != is_fav:
                try:
                    recipes_df.at[index, 'Favorite'] = new_fav
                    conn.update(spreadsheet=SHEET_URL, worksheet="Recipes", data=recipes_df.drop(columns=['Sort_Score']))
                    st.success("Favorite Updated!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Update failed: {e}")

            st.write(f"**Ingredients:** {raw_ingreds}")
            
            if st.button(f"Cook {row['Meal_Name']}", key=f"btn_{index}"):
                try:
                    # Deduct Pantry
                    for item in ing_list:
                        if ":" in item:
                            n, q = item.split(":")
                            pantry[n.strip()] -= int(q.strip())
                    
                    # Update History
                    new_log = pd.DataFrame([[row['Meal_Name'], datetime.now().strftime("%Y-%m-%d")]], 
                                         columns=['Meal_Name', 'Date_Cooked'])
                    updated_h = pd.concat([history_df, new_log], ignore_index=True)
                    
                    # Sync to Sheets
                    conn.update(spreadsheet=SHEET_URL, worksheet="Pantry", data=pd.DataFrame(list(pantry.items()), columns=['Ingredient', 'Amount']))
                    conn.update(spreadsheet=SHEET_URL, worksheet="History", data=updated_h)
                    
                    st.balloons()
                    st.rerun()
                except Exception as e:
                    st.error(f"Cooking update failed: {e}")

    # --- 5. SIDEBAR ---
    with st.sidebar:
        st.header("🏠 Pantry Inventory")
        st.write(pantry)
        
        st.divider()
        st.header("📜 Cooking History")
        if not history_df.empty:
            # We show the last 5 entries
            st.table(history_df.sort_values(by='Date_Cooked', ascending=False).head(5))
        else:
            st.info("No history found in 'History' tab.")
