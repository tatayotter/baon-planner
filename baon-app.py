import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# --- APP CONFIG ---
st.set_page_config(
    page_title="Pinoy Baon Master",
    page_icon="🍱",
    layout="centered"
)

# --- 1. CONNECTION & SHEET LINK ---
# Ensure this matches your actual Sheet URL
SHEET_URL = "https://docs.google.com/spreadsheets/d/1DgVuak6x-AHQcltPoK8fB25T644lTUbkeiH3E3KiMYc/edit"

conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. LOAD DATA ---
try:
    # Reading tabs - Names must be exactly "Pantry" and "Recipes"
    pantry_df = conn.read(spreadsheet=SHEET_URL, worksheet="Pantry", ttl=0)
    recipes_df = conn.read(spreadsheet=SHEET_URL, worksheet="Recipes", ttl=0)
    
    # Cleaning data
    pantry_df = pantry_df.dropna(subset=['Ingredient'])
    recipes_df = recipes_df.dropna(subset=['Meal_Name'])
    
    # Create dictionary for logic: { 'Chicken': 1000, 'Eggs': 12 }
    pantry = pantry_df.set_index('Ingredient')['Amount'].to_dict()
except Exception as e:
    st.error("⚠️ Connection Error!")
    st.info("Check: Is the sheet shared with your Service Account email as Editor?")
    st.code(e)
    st.stop()

# --- 3. UI HEADER ---
st.title("🍱 Pinoy Baon Master")
st.write(f"Planning for your 7 & 9 year olds.")

# Toggle for Picky Eaters
picky_mode = st.toggle("Picky Eater Mode (Kids Only)", value=True)

# --- 4. HELPER LOGIC ---
def can_cook(ingredients_str):
    """Checks if current pantry has enough for the recipe"""
    try:
        items = ingredients_str.split(",")
        for pair in items:
            name, qty = pair.split(":")
            needed = int(qty.strip())
            if pantry.get(name.strip(), 0) < needed:
                return False
        return True
    except:
        return False

# --- 5. MAIN DISPLAY: MEAL SELECTION ---
st.subheader("🍳 Available Meals")
st.caption("Click a meal to see the ingredients list.")

found_any = False
for _, row in recipes_df.iterrows():
    # Filter by Picky Mode
    if picky_mode and not row['Picky_Friendly']:
        continue
    
    # Check if ingredients are sufficient
    if can_cook(row['Ingredients_List']):
        found_any = True
        with st.expander(f"✅ {row['Meal_Name']}"):
            st.write("**Ingredients Required:**")
            
            # --- FORMATTED LIST DISPLAY ---
            ingredient_items = row['Ingredients_List'].split(",")
            for item in ingredient_items:
                st.write(f"• {item.strip()}")
            
            if st.button(f"Cook {row['Meal_Name']}", key=row['Meal_Name']):
                # Deduct ingredients from the local dictionary
                for pair in ingredient_items:
                    name, qty = pair.split(":")
                    pantry[name.strip()] -= int(qty.strip())
                
                # Push updated levels back to Google Sheets
                final_df = pd.DataFrame(list(pantry.items()), columns=['Ingredient', 'Amount'])
                conn.update(spreadsheet=SHEET_URL, worksheet="Pantry", data=final_df)
                
                st.balloons()
                st.success(f"Deducted ingredients for {row['Meal_Name']}!")
                st.rerun()

if not found_any:
    st.warning("No meals available. Check your Pantry stock or add more recipes!")

# --- 6. SIDEBAR: INVENTORY VIEW ---
with st.sidebar:
    st.header("🏠 Current Pantry")
    st.write("Live stock levels from your sheet.")
    
    # Display inventory with color coding for low stock
    for item, qty in pantry.items():
        if qty <= 0:
            st.error(f"{item}: {qty} (OUT)")
        elif qty < 100:
            st.warning(f"{item}: {qty} (LOW)")
        else:
            st.write(f"**{item}**: {qty}")
            
    if st.button("🔄 Refresh Data"):
        st.rerun()

# --- 7. SHOPPING LIST ---
st.divider()
st.subheader("🛒 Shopping List")
out_of_stock = [item for item, qty in pantry.items() if qty <= 0]

if out_of_stock:
    for item in out_of_stock:
        st.write(f"- [ ] **{item}**")
else:
    st.success("Everything is in stock!")
