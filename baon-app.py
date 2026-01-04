import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# --- APP CONFIG ---
st.set_page_config(page_title="Pinoy Baon Master", page_icon="🍱")

# --- 1. CONNECTION ---
conn = st.connection("gsheets", type=GSheetsConnection)

# Your specific sheet link
SHEET_URL = "https://docs.google.com/spreadsheets/d/1DgVuak6x-AHQcltPoK8fB25T644lTUbkeiH3E3KiMYc/edit"

# --- 2. LOAD DATA ---
try:
    # Attempting to read both worksheets from your specific URL
    pantry_df = conn.read(spreadsheet=SHEET_URL, worksheet="Pantry", ttl=0)
    recipes_df = conn.read(spreadsheet=SHEET_URL, worksheet="Recipes", ttl=0)
    
    # Clean and process data
    pantry_df = pantry_df.dropna(subset=['Ingredient'])
    pantry = pantry_df.set_index('Ingredient')['Amount'].to_dict()
    
except Exception as e:
    st.error("⚠️ Connection Failed!")
    st.write("### Specific Error Log:")
    st.code(f"{e}")
    st.write("---")
    st.write("**Quick Check:** Is the sheet shared with your Service Account email as an Editor?")
    st.stop()

# --- 3. UI RENDER ---
st.title("🍱 Pinoy Baon Master")
picky_mode = st.toggle("Picky Eater Mode", value=True)

st.subheader("🍳 Available Meals")

def can_cook(ingredients_str):
    try:
        for pair in ingredients_str.split(","):
            name, qty = pair.split(":")
            if pantry.get(name.strip(), 0) < int(qty.strip()):
                return False
        return True
    except: return False

found_any = False
for _, row in recipes_df.iterrows():
    if picky_mode and not row['Picky_Friendly']:
        continue
    
    if can_cook(row['Ingredients_List']):
        found_any = True
        if st.button(f"Cook {row['Meal_Name']}"):
            for pair in row['Ingredients_List'].split(","):
                name, qty = pair.split(":")
                pantry[name.strip()] -= int(qty.strip())
            
            # Save the new pantry levels back to Google Sheets
            updated_df = pd.DataFrame(list(pantry.items()), columns=['Ingredient', 'Amount'])
            conn.update(spreadsheet=SHEET_URL, worksheet="Pantry", data=updated_df)
            st.success(f"Success! {row['Meal_Name']} cooked.")
            st.rerun()

if not found_any:
    st.info("No meals currently available. Check your inventory or add new recipes in Google Sheets!")
