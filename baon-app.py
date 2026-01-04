import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, timedelta

# --- 1. CONNECTION & CONFIG ---
st.set_page_config(page_title="Pinoy Baon Master", page_icon="🍱", layout="wide")

url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- 2. DATA LOADING & NORMALIZATION ---
def load_all_data():
    try:
        p_res = supabase.table("pantry").select("*").execute()
        r_res = supabase.table("recipes").select("*").execute()
        h_res = supabase.table("history").select("*").execute()
        
        p_df = pd.DataFrame(p_res.data) if p_res.data else pd.DataFrame(columns=['ingredient', 'amount'])
        r_df = pd.DataFrame(r_res.data) if r_res.data else pd.DataFrame()
        h_df = pd.DataFrame(h_res.data) if h_res.data else pd.DataFrame(columns=['meal_name', 'date_cooked'])
        
        for df in [p_df, r_df, h_df]:
            if not df.empty:
                df.columns = [str(c).lower().strip().replace(" ", "_") for c in df.columns]
                
        return p_df, r_df, h_df
    except Exception as e:
        st.error(f"Database Error: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

p_df, r_df, h_df = load_all_data()
pantry_dict = {str(k).lower().strip(): v for k, v in p_df.set_index('ingredient')['amount'].to_dict().items()} if not p_df.empty else {}

# --- 3. COOLDOWN LOGIC ---
recent_meals = []
if not h_df.empty:
    h_df['date_cooked'] = pd.to_datetime(h_df['date_cooked'])
    limit = datetime.now() - timedelta(days=5)
    recent_meals = [str(m).lower().strip() for m in h_df[h_df['date_cooked'] > limit]['meal_name'].unique()]

# --- 4. SIDEBAR ---
with st.sidebar:
    st.header("🏠 Pantry Inventory")
    if not p_df.empty:
        edited_pantry = st.data_editor(p_df, hide_index=True, key="pantry_editor")
        if st.button("Save Pantry Changes"):
            for _, row in edited_pantry.iterrows():
                supabase.table("pantry").update({"amount": row['amount']}).eq("ingredient", row['ingredient']).execute()
            st.rerun()
    
    st.divider()
    st.header("📜 History")
    if not h_df.empty:
        st.dataframe(h_df.sort_values('date_cooked', ascending=False).head(10), hide_index=True)

# --- 5. MAIN UI ---
st.title("🍱 Pinoy Baon Master")
picky_mode = st.toggle("Picky Eater Mode (Kids Friendly)", value=True)

if r_df.empty:
    st.info("No recipes found in Supabase.")
else:
    # Ranking
    r_df['rank'] = r_df.apply(lambda x: 0 if str(x.get('meal_name', '')).lower().strip() in recent_meals else (2 if x.get('favorite', False) else 1), axis=1)
    sorted_recipes = r_df.sort_values(['rank', 'meal_name'], ascending=[False, True])

    # --- CATEGORIZATION LOGIC ---
    ready_to_cook = []
    missing_ingredients = []

    for _, row in sorted_recipes.iterrows():
        meal_name = str(row.get('meal_name', 'Unknown'))
        is_picky = str(row.get('picky_friendly', 'false')).lower() == 'true'
        
        if picky_mode and not is_picky:
            continue
        
        raw_ings = str(row.get('ingredients_list', '')).split(",")
        parsed_ings = []
        can_cook = True
        
        for item in raw_ings:
            if ":" in item:
                name_part, qty_part = item.split(":")
                name = name_part.strip()
                try:
                    req_qty = int(qty_part.strip())
                    actual_qty = pantry_dict.get(name.lower(), 0)
                    has_enough = actual_qty >= req_qty
                    if not has_enough: can_cook = False
                    
                    parsed_ings.append({
                        "display": f"{name}: {req_qty} (Have: {actual_qty})",
                        "status": "✅" if has_enough else "❌"
                    })
                except:
                    can_cook = False
        
        meal_data = {"row": row, "parsed_ings": parsed_ings, "meal_name": meal_name}
        if can_cook:
            ready_to_cook.append(meal_data)
        else:
            missing_ingredients.append(meal_data)

    # --- DISPLAY TABS ---
    tab1, tab2 = st.tabs([f"✅ Ready to Cook ({len(ready_to_cook)})", f"🛒 Missing Ingredients ({len(missing_ingredients)})"])

    with tab1:
        if not ready_to_cook:
            st.warning("Nothing ready to cook! Check your pantry or 'Missing Ingredients' tab.")
        else:
            cols = st.columns(2)
            for i, meal in enumerate(ready_to_cook):
                with cols[i % 2].expander(f"🍲 {meal['meal_name']}"):
                    for ing in meal['parsed_ings']:
                        st.write(f"{ing['status']} {ing['display']}")
                    
                    if st.button(f"Cook {meal['meal_name']}", key=f"ready_{meal['meal_name']}"):
                        # Deduct and Log logic...
                        for item in str(meal['row']['ingredients_list']).split(","):
                            if ":" in item:
                                n, q = item.split(":")
                                n = n.strip()
                                new_val = int(pantry_dict[n.lower()]) - int(q.strip())
                                supabase.table("pantry").update({"amount": new_val}).eq("ingredient", n).execute()
                        supabase.table("history").insert({"meal_name": meal['meal_name'], "date_cooked": datetime.now().strftime("%Y-%m-%d")}).execute()
                        st.balloons()
                        st.rerun()

    with tab2:
        if not missing_ingredients:
            st.success("You have everything for all your recipes!")
        else:
            cols = st.columns(2)
            for i, meal in enumerate(missing_ingredients):
                with cols[i % 2].expander(f"❌ {meal['meal_name']}"):
                    st.write("**Missing Items:**")
                    for ing in meal['parsed_ings']:
                        st.write(f"{ing['status']} {ing['display']}")
                    st.button(f"Cannot Cook (Missing Ingredients)", key=f"missing_{meal['meal_name']}", disabled=True)
