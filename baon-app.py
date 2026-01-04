import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, timedelta

# --- 1. CONNECTION ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- 2. DATA LOADING & NORMALIZATION ---
def load_and_clean_data():
    # Fetch
    p_res = supabase.table("pantry").select("*").execute()
    r_res = supabase.table("recipes").select("*").execute()
    h_res = supabase.table("history").select("*").execute()
    
    # Convert to DataFrames
    p_df = pd.DataFrame(p_res.data) if p_res.data else pd.DataFrame()
    r_df = pd.DataFrame(r_res.data) if r_res.data else pd.DataFrame()
    h_df = pd.DataFrame(h_res.data) if h_res.data else pd.DataFrame()
    
    # NORMALIZATION: Force all columns to lowercase and remove hidden spaces
    for df in [p_df, r_df, h_df]:
        if not df.empty:
            df.columns = [str(c).lower().strip().replace(" ", "_") for c in df.columns]
            
    return p_df, r_df, h_df

p_df, r_df, h_df = load_and_clean_data()

# --- 3. PANTRY SAFETY CHECK ---
if p_df.empty:
    st.warning("Pantry is empty. Please add items in Supabase.")
    pantry_dict = {}
else:
    # We use .get() to avoid crash if the column name is still slightly off
    try:
        pantry_dict = p_df.set_index('ingredient')['amount'].to_dict()
    except KeyError:
        st.error(f"Could not find 'ingredient' column. Found: {p_df.columns.tolist()}")
        st.stop()

# --- 4. COOLDOWN LOGIC ---
recent_meals = []
if not h_df.empty and 'meal_name' in h_df.columns:
    # Ensure date_cooked is the right format
    h_df['date_cooked'] = pd.to_datetime(h_df.get('date_cooked', datetime.now()))
    limit = datetime.now() - timedelta(days=5)
    recent_meals = h_df[h_df['date_cooked'] > limit]['meal_name'].unique()

# --- 5. MAIN UI ---
st.title("🍱 Pinoy Baon Master")
picky_mode = st.toggle("Picky Eater Mode", value=True)

if r_df.empty:
    st.info("No recipes found. Add some in Supabase!")
else:
    # Ranking logic
    r_df['rank'] = r_df.apply(lambda x: 0 if x.get('meal_name') in recent_meals else (2 if x.get('favorite', False) else 1), axis=1)
    sorted_recipes = r_df.sort_values('rank', ascending=False)

    for _, row in sorted_recipes.iterrows():
        # Picky Filter (Case-insensitive)
        picky_val = str(row.get('picky_friendly', 'false')).lower() == 'true'
        if picky_mode and not picky_val:
            continue
        
        # Stock Check
        ing_text = str(row.get('ingredients_list', ''))
        ings = [i.strip() for i in ing_text.split(",")]
        can_cook = True
        for itm in ings:
            if ":" in itm:
                name, qty = itm.split(":")
                name = name.strip()
                if pantry_dict.get(name, 0) < int(qty.strip()):
                    can_cook = False

        if can_cook:
            label = f"{'⏳' if row['rank']==0 else '⭐' if row['rank']==2 else '🍲'} {row.get('meal_name', 'Unknown')}"
            with st.expander(label):
                st.write(f"**Ingredients:** {ing_text}")
                if st.button(f"Cook {row.get('meal_name')}", key=f"btn_{row.get('id')}"):
                    try:
                        # 1. Update Pantry in Supabase
                        for itm in ings:
                            if ":" in itm:
                                name, qty = itm.split(":")
                                name = name.strip()
                                new_val = int(pantry_dict[name]) - int(qty.strip())
                                supabase.table("pantry").update({"amount": new_val}).eq("ingredient", name).execute()
                        
                        # 2. Log History
                        supabase.table("history").insert({"meal_name": row['meal_name']}).execute()
                        
                        st.balloons()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Update failed: {e}")

# --- 6. SIDEBAR ---
with st.sidebar:
    st.header("🏠 Pantry")
    st.dataframe(p_df, hide_index=True)
    st.header("📜 History")
    if not h_df.empty:
        st.dataframe(h_df.sort_values('date_cooked', ascending=False).head(10), hide_index=True)
