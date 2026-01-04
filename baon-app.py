import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, timedelta

# --- 1. INITIALIZATION ---
st.set_page_config(page_title="Pinoy Baon Master", page_icon="🍱")

url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- 2. DATA FETCHING ---
def load_data():
    # Fetch all data from Supabase
    p_res = supabase.table("pantry").select("*").execute()
    r_res = supabase.table("recipes").select("*").execute()
    h_res = supabase.table("history").select("*").execute()
    
    return (
        pd.DataFrame(p_res.data),
        pd.DataFrame(r_res.data),
        pd.DataFrame(h_res.data)
    )

p_df, r_df, h_df = load_data()

# Prepare Pantry Dictionary
pantry_dict = p_df.set_index('ingredient')['amount'].to_dict()

# --- 3. SORTING & COOLDOWN ---
if not h_df.empty:
    h_df['date_cooked'] = pd.to_datetime(h_df['date_cooked'])
    cooldown_limit = datetime.now() - timedelta(days=5)
    recent_meals = h_df[h_df['date_cooked'] > cooldown_limit]['meal_name'].unique()
else:
    recent_meals = []

def get_priority(row):
    if row['meal_name'] in recent_meals: return 0
    return 2 if row.get('favorite') else 1

r_df['score'] = r_df.apply(get_priority, axis=1)
r_df = r_df.sort_values('score', ascending=False)

# --- 4. MAIN UI ---
st.title("🍱 Pinoy Baon Master")
picky_mode = st.toggle("Picky Eater Mode", value=True)

for _, row in r_df.iterrows():
    if picky_mode and not row['picky_friendly']: continue
    
    # Check if we have ingredients
    ing_list = [i.strip() for i in str(row['ingredients_list']).split(",")]
    can_cook = True
    for item in ing_list:
        if ":" in item:
            name, qty = item.split(":")
            if pantry_dict.get(name.strip(), 0) < int(qty.strip()):
                can_cook = False

    if can_cook:
        icon = "⏳" if row['meal_name'] in recent_meals else ("⭐" if row['score'] == 2 else "🍲")
        with st.expander(f"{icon} {row['meal_name']}"):
            st.write(f"**Ingredients:** {row['ingredients_list']}")
            
            if st.button(f"Cook {row['meal_name']}", key=f"cook_{row['id']}"):
                # ACTION: Update Database
                try:
                    # 1. Deduct Pantry
                    for item in ing_list:
                        if ":" in item:
                            n, q = item.split(":")
                            new_val = int(pantry_dict[n.strip()]) - int(q.strip())
                            supabase.table("pantry").update({"amount": new_val}).eq("ingredient", n.strip()).execute()
                    
                    # 2. Log History
                    supabase.table("history").insert({
                        "meal_name": row['meal_name'], 
                        "date_cooked": datetime.now().strftime("%Y-%m-%d")
                    }).execute()
                    
                    st.success("Database updated instantly!")
                    st.balloons()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("🏠 Pantry")
    st.dataframe(p_df, hide_index=True)
    st.header("📜 Recent History")
    if not h_df.empty:
        st.dataframe(h_df.sort_values('date_cooked', ascending=False).head(5), hide_index=True)
