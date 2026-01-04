import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, timedelta

# --- 1. CONNECTION & CONFIG ---
st.set_page_config(page_title="Pinoy Baon Master", page_icon="🍱", layout="wide")

# Initialize Supabase
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- 2. DATA LOADING & CLEANING ---
def load_all_data():
    try:
        p_res = supabase.table("pantry").select("*").execute()
        r_res = supabase.table("recipes").select("*").execute()
        h_res = supabase.table("history").select("*").execute()
        
        p_df = pd.DataFrame(p_res.data) if p_res.data else pd.DataFrame(columns=['ingredient', 'amount'])
        r_df = pd.DataFrame(r_res.data) if r_res.data else pd.DataFrame()
        h_df = pd.DataFrame(h_res.data) if h_res.data else pd.DataFrame(columns=['meal_name', 'date_cooked'])
        
        # Normalize columns (lowercase and strip spaces)
        for df in [p_df, r_df, h_df]:
            if not df.empty:
                df.columns = [str(c).lower().strip().replace(" ", "_") for c in df.columns]
                
        return p_df, r_df, h_df
    except Exception as e:
        st.error(f"Database Error: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

p_df, r_df, h_df = load_all_data()

# Create a normalized pantry dictionary for logic
# Key: 'rice', Value: 5
pantry_dict = {str(k).lower().strip(): v for k, v in p_df.set_index('ingredient')['amount'].to_dict().items()} if not p_df.empty else {}

# --- 3. COOLDOWN LOGIC ---
recent_meals = []
if not h_df.empty:
    h_df['date_cooked'] = pd.to_datetime(h_df['date_cooked'])
    cooldown_date = datetime.now() - timedelta(days=5)
    recent_meals = [str(m).lower() for m in h_df[h_df['date_cooked'] > cooldown_date]['meal_name'].unique()]

# --- 4. SIDEBAR (Inventory & History) ---
with st.sidebar:
    st.header("🏠 Pantry Inventory")
    
    if not p_df.empty:
        # Editable Pantry
        st.subheader("Edit Quantities")
        edited_pantry = st.data_editor(
            p_df, 
            column_config={"amount": st.column_config.NumberColumn(min_value=0)},
            hide_index=True,
            key="pantry_editor"
        )
        if st.button("Save Pantry Changes"):
            for _, row in edited_pantry.iterrows():
                supabase.table("pantry").update({"amount": row['amount']}).eq("ingredient", row['ingredient']).execute()
            st.success("Saved!")
            st.rerun()
    
    st.divider()
    
    # Add New Item Form
    st.subheader("➕ Add New Item")
    with st.form("add_item", clear_on_submit=True):
        new_name = st.text_input("Item Name")
        new_qty = st.number_input("Starting Qty", min_value=0)
        if st.form_submit_button("Add to Database"):
            if new_name:
                supabase.table("pantry").insert({"ingredient": new_name, "amount": new_qty}).execute()
                st.rerun()

    st.divider()
    st.header("📜 History")
    if not h_df.empty:
        st.dataframe(h_df.sort_values('date_cooked', ascending=False).head(10), hide_index=True)

# --- 5. MAIN UI (Meal Suggestions) ---
st.title("🍱 Pinoy Baon Master")
picky_mode = st.toggle("Picky Eater Mode (Kids Friendly)", value=True)

if r_df.empty:
    st.info("No recipes found. Add some in your Supabase 'recipes' table!")
else:
    # Rank: 0 = Recent (Cooldown), 2 = Favorite, 1 = Normal
    r_df['rank'] = r_df.apply(lambda x: 0 if str(x.get('meal_name', '')).lower() in recent_meals else (2 if x.get('favorite', False) else 1), axis=1)
    sorted_recipes = r_df.sort_values('rank', ascending=False)

    cols = st.columns(2)
    col_idx = 0

    for _, row in sorted_recipes.iterrows():
        # Picky Filter
        is_picky = str(row.get('picky_friendly', 'false')).lower() == 'true'
        if picky_mode and not is_picky:
            continue
        
        # STOCK CHECK LOGIC
        ing_text = str(row.get('ingredients_list', ''))
        ings = [i.strip() for i in ing_text.split(",")]
        can_cook = True
        
        for itm in ings:
            if ":" in itm:
                name_part, qty_part = itm.split(":")
                req_name = name_part.strip().lower()
                try:
                    req_qty = int(qty_part.strip())
                    if pantry_dict.get(req_name, 0) < req_qty:
                        can_cook = False
                except ValueError:
                    can_cook = False

        if can_cook:
            with cols[col_idx % 2].expander(f"{'⏳' if row['rank']==0 else '⭐' if row['rank']==2 else '🍲'} {row['meal_name']}"):
                st.write(f"**Required:** {ing_text}")
                if st.button(f"Cook {row['meal_name']}", key=f"cook_{row['id']}"):
                    # 1. Update Pantry (Deduct)
                    for itm in ings:
                        if ":" in itm:
                            name_part, qty_part = itm.split(":")
                            name = name_part.strip()
                            new_val = int(pantry_dict[name.lower()]) - int(qty_part.strip())
                            supabase.table("pantry").update({"amount": new_val}).eq("ingredient", name).execute()
                    
                    # 2. Log History
                    supabase.table("history").insert({"meal_name": row['meal_name']}).execute()
                    
                    st.balloons()
                    st.rerun()
            col_idx += 1
