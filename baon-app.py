import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# --- APP CONFIG ---
st.set_page_config(
    page_title="Pinoy Baon Master",
    page_icon="🍱",
    layout="centered"
)

# --- 1. CONNECT TO GOOGLE SHEETS ---
# This uses the 'secrets' you set up in Streamlit Cloud
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. LOAD DATA ---
try:
    pantry_df = conn.read(worksheet="Pantry", ttl=0) # ttl=0 ensures fresh data
    recipes_df = conn.read(worksheet="Recipes", ttl=0)
    
    # Clean up data (remove empty rows/cols)
    pantry_df = pantry_df.dropna(subset=['Ingredient'])
    recipes_df = recipes_df.dropna(subset=['Meal_Name'])
    
    # Convert Pantry to a dictionary for logic
    pantry = pantry_df.set_index('Ingredient')['Amount'].to_dict()
except Exception as e:
    st.error("Could not connect to Google Sheets. Check your Secrets and Sheet names.")
    st.stop()

# --- 3. UI HEADER ---
st.title("🍱 Pinoy Baon Master")
st.write("Smart lunch planning for the kids.")

# Toggle for Picky Eaters
picky_mode = st.toggle("Picky Eater Mode (Kids Only)", value=True)

# --- 4. SIDEBAR: INVENTORY MANAGEMENT ---
with st.sidebar:
    st.header("🏠 Pantry Stock")
    st.info("Update weights here after grocery shopping.")
    
    new_pantry_values = {}
    for item, qty in pantry.items():
        new_pantry_values[item] = st.number_input(f"{item}", value=int(qty), step=1)
    
    if st.button("💾 Save Manual Updates"):
        updated_df = pd.DataFrame(list(new_pantry_values.items()), columns=['Ingredient', 'Amount'])
        conn.update(worksheet="Pantry", data=updated_df)
        st.success("Pantry saved to Google Sheets!")
        st.rerun()

# --- 5. LOGIC: RECIPE PARSER ---
def can_cook(ingredients_str):
    """Checks if current pantry has enough for the recipe string 'Item:Qty, Item:Qty'"""
    try:
        items = ingredients_str.split(",")
        for pair in items:
            name, qty = pair.split(":")
            name = name.strip()
            needed = int(qty.strip())
            if pantry.get(name, 0) < needed:
                return False
        return True
    except:
        return False

# --- 6. MAIN DISPLAY: POSSIBLE MEALS ---
st.subheader("🍳 Available Meals")

possible_meals = []
for _, row in recipes_df.iterrows():
    # Filter by Picky Mode
    if picky_mode and not row['Picky_Friendly']:
        continue
    
    # Check if ingredients are sufficient
    if can_cook(row['Ingredients_List']):
        possible_meals.append(row)

if possible_meals:
    for meal in possible_meals:
        with st.expander(f"✅ {meal['Meal_Name']}"):
            st.write(f"**Ingredients:** {meal['Ingredients_List']}")
            
            if st.button(f"Cook {meal['Meal_Name']}", key=meal['Meal_Name']):
                # Deduct ingredients from the local dictionary
                items = meal['Ingredients_List'].split(",")
                for pair in items:
                    name, qty = pair.split(":")
                    name = name.strip()
                    pantry[name] -= int(qty.strip())
                
                # Push updated dictionary back to Google Sheets
                final_df = pd.DataFrame(list(pantry.items()), columns=['Ingredient', 'Amount'])
                conn.update(worksheet="Pantry", data=final_df)
                
                st.balloons()
                st.success(f"Deducted ingredients for {meal['Meal_Name']}!")
                st.rerun()
else:
    st.warning("No meals available. Update your Pantry or add more recipes to the Google Sheet!")

# --- 7. SHOPPING LIST ---
st.divider()
st.subheader("🛒 Shopping List")
out_of_stock = [item for item, qty in pantry.items() if qty <= 0]

if out_of_stock:
    for item in out_of_stock:
        st.error(f"⚠️ Out of stock: **{item}**")
else:
    st.success("Pantry is well-stocked!")

st.caption("Tip: You can add new recipes directly to your Google Sheet 'Recipes' tab and they will appear here.")