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
    # This reads the URL directly from your Secrets for maximum security
    pantry_df = conn.read(worksheet="Pantry", ttl=0)
    recipes_df = conn.read(worksheet="Recipes", ttl=0)
    
    # Check if we actually got data
    if pantry_df.empty or recipes_df.empty:
        st.error("The Sheet is connected, but the tabs 'Pantry' or 'Recipes' seem to be empty!")
        st.stop()

    pantry = pantry_df.set_index('Ingredient')['Amount'].to_dict()
    
except Exception as e:
    st.error("⚠️ Connection Still Failing")
    st.info("Check: Did you click 'Share' in the Sheet and add the email as EDITOR?")
    st.code(f"Error Message: {e}")
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

