import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta

# --- 1. APP CONFIGURATION ---
st.set_page_config(
    page_title="Pinoy Baon Master",
    page_icon="🍱",
    layout="centered"
)

# --- 2. CONNECTION & DATA LOADING ---
# Ensure this matches your specific Sheet URL
SHEET_URL = "https://docs.google.com/spreadsheets/d/1DgVuak6x-AHQcltPoK8fB25T644lTUbkeiH3E3KiMYc/edit"
conn = st.connection("gsheets", type=GSheetsConnection)

try:
    # Load all three worksheets
    pantry_df = conn.read(spreadsheet=SHEET_URL, worksheet="Pantry", ttl=0)
    recipes_df = conn.read(spreadsheet=SHEET_URL, worksheet="Recipes", ttl=0)
    
    try:
        history_df = conn.read(spreadsheet=SHEET_URL, worksheet="History", ttl=0)
    except:
        # Create empty history if tab exists but has no data yet
        history_df = pd.DataFrame(columns=['Meal_Name', 'Date_Cooked'])

    # Data Cleaning
    pantry_df = pantry_df.dropna(subset=['Ingredient'])
    recipes_df = recipes_df.dropna(subset=['Meal_Name'])
    pantry = pantry_df.set_index('Ingredient')['Amount'].to_dict()

except Exception as e:
    st.error("⚠️ Connection Error! Please check your Google Sheet tabs and Service Account permissions.")
    st.stop()

# --- 3. SORTING LOGIC (Cooldown vs. Favorites) ---
# Convert history dates to datetime objects for calculation
history_df['Date_Cooked'] = pd.to_datetime(history_df['Date_Cooked'])
five_days_ago = datetime.now() - timedelta(days=5)

# Identify meals cooked in the last 5 days
recent_meals = history_df[history_df['Date_Cooked'] > five_days_ago]['Meal_Name'].unique()

def get_sort_score(row):
    """
    Priority Hierarchy:
    Score 0: Recently Cooked (Always at the bottom)
    Score 2: Favorite AND not recently cooked (Top)
    Score 1: Standard meal AND not recently cooked (Middle)
    """
    if row['Meal_Name'] in recent_meals:
        return 0  # Forced to the bottom
    
    # Handle both Boolean and String "TRUE" from Google Sheets
    is_fav = str(row.get('Favorite')).upper() == 'TRUE'
    if is_fav:
        return 2  # Priority
    return 1      # Normal

recipes_df['Sort_Score'] = recipes_df.apply(get_sort_score, axis=1)
sorted_recipes = recipes_df.sort_values(by='Sort_Score', ascending=False)

# --- 4. HELPER FUNCTIONS ---
def can_cook(ingredients_str):
    """Checks if enough ingredients exist in the pantry dictionary."""
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

# --- 5. MAIN UI ---
st.title("🍱 Pinoy Baon Master")
st.write(f"Today is {datetime.now().strftime('%A, %b %d, %Y')}")

# User Controls
picky_mode = st.toggle("Picky Eater Mode (Kids Only)", value=True)

st.subheader("🍳 Available Meals")
st.caption("Favorites ⭐ are at the top. Meals cooked within the last 5 days ⏳ move to the bottom.")



found_any = False
for index, row in sorted_recipes.iterrows():
    # Filter by Picky Mode
    if picky_mode and not row['Picky_Friendly']:
        continue
    
    # Only display if we have ingredients
    if can_cook(row['Ingredients_List']):
        found_any = True
        
        is_fav = str(row.get('Favorite')).upper() == 'TRUE'
        is_recent = row['Meal_Name'] in recent_meals
        
        # Determine Label Icon
        if is_recent:
            display_label = f"⏳ {row['Meal_Name']} (Cooldown)"
        elif is_fav:
            display_label = f"⭐ {row['Meal_Name']}"
        else:
            display_label = row['Meal_Name']

        with st.expander(display_label):
            # FAVORITE TOGGLE
            # checkbox key uses index to ensure uniqueness
            new_fav_state = st.checkbox("Mark as Favorite", value=is_fav, key=f"fav_{index}")
            
            if new_fav_state != is_fav:
                # Update the source dataframe
                recipes_df.at[index, 'Favorite'] = new_fav_state
                # Remove Sort_Score before saving back to GSheets
                save_df = recipes_df.drop(columns=['Sort_Score'])
                conn.update(spreadsheet=SHEET_URL, worksheet="Recipes", data=save_df)
                st.rerun()

            st.write("**Ingredients Required:**")
            ingredient_items = row['Ingredients_List'].split(",")
            for item in ingredient_items:
                st.write(f"• {item.strip()}")
            
            # COOK BUTTON
            if st.button(f"Cook {row['Meal_Name']}", key=f"btn_{index}"):
                # 1. Deduct from local dictionary
                for pair in ingredient_items:
                    name, qty = pair.split(":")
                    pantry[name.strip()] -= int(qty.strip())
                
                # 2. Add entry to History
                new_log = pd.DataFrame([[row['Meal_Name'], datetime.now().strftime("%Y-%m-%d %H:%M:%S")]], 
                                     columns=['Meal_Name', 'Date_Cooked'])
                updated_history = pd.concat([history_df, new_log], ignore_index=True)
                
                # 3. Batch Update Google Sheets
                updated_pantry_df = pd.DataFrame(list(pantry.items()), columns=['Ingredient', 'Amount'])
                conn.update(spreadsheet=SHEET_URL, worksheet="Pantry", data=updated_pantry_df)
                conn.update(spreadsheet=SHEET_URL, worksheet="History", data=updated_history)
                
                st.balloons()
                st.rerun()

if not found_any:
    st.info("No meals currently available based on your pantry stock.")

# --- 6. SIDEBAR: INVENTORY TRACKER ---
with st.sidebar:
    st.header("🏠 Pantry Inventory")
    st.write("Current stock levels:")
    
    for item, qty in pantry.items():
        if qty <= 0:
            st.error(f"{item}: {qty}")
        elif qty < 100:
            st.warning(f"{item}: {qty}")
        else:
            st.write(f"**{item}**: {qty}")
            
    st.divider()
    if st.button("🔄 Sync with Google Sheets"):
        st.rerun()
