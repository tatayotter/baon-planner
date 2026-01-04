import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, timedelta

# --- 1. CONNECTION & CONFIG ---
st.set_page_config(page_title="Tatay's Baon Planner", page_icon="🍱", layout="wide")

url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- 2. DATA LOADING & NORMALIZATION ---
def load_all_data():
    try:
        p_res = supabase.table("pantry").select("*").execute()
        r_res = supabase.table("recipes").select("*").execute()
        h_res = supabase.table("history").select("*").execute()
        pl_res = supabase.table("planner").select("*").execute()
        
        p_df = pd.DataFrame(p_res.data) if p_res.data else pd.DataFrame(columns=['ingredient', 'amount'])
        r_df = pd.DataFrame(r_res.data) if r_res.data else pd.DataFrame()
        h_df = pd.DataFrame(h_res.data) if h_res.data else pd.DataFrame(columns=['meal_name', 'date_cooked'])
        
        # Planner sorting
        pl_df = pd.DataFrame(pl_res.data) if pl_res.data else pd.DataFrame(columns=['day_name', 'meal_name'])
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        if not pl_df.empty:
            pl_df['day_name'] = pd.Categorical(pl_df['day_name'], categories=day_order, ordered=True)
            pl_df = pl_df.sort_values('day_name')
                
        for df in [p_df, r_df, h_df, pl_df]:
            if not df.empty:
                df.columns = [str(c).lower().strip().replace(" ", "_") for c in df.columns]
                
        return p_df, r_df, h_df, pl_df
    except Exception as e:
        st.error(f"Database Error: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

p_df, r_df, h_df, pl_df = load_all_data()
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

# --- 5. WEEKLY MENU BOARD ---
st.title("🍱 Tatay's Baon Planner")

header_col, btn_col = st.columns([4, 1])
with header_col:
    st.header("🗓️ This Week's School Menu")
with btn_col:
    st.write("##") 
    if st.button("🗑️ Clear Week"):
        supabase.table("planner").update({"meal_name": None}).neq("day_name", "dummy").execute()
        st.toast("Menu cleared!")
        st.rerun()

plan_cols = st.columns(5)
days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

for i, day in enumerate(days):
    with plan_cols[i]:
        st.markdown(f"**{day}**")
        current_row = pl_df[pl_df['day_name'] == day]
        current_val = current_row['meal_name'].values[0] if not current_row.empty and pd.notna(current_row['meal_name'].values[0]) else "None"
        
        recipe_options = ["None"] + sorted(r_df['meal_name'].tolist()) if not r_df.empty else ["None"]
        try:
            current_index = recipe_options.index(current_val)
        except ValueError:
            current_index = 0

        choice = st.selectbox(f"Assign {day}", recipe_options, index=current_index, key=f"plan_{day}", label_visibility="collapsed")
        
        if choice != current_val:
            new_val = choice if choice != "None" else None
            supabase.table("planner").upsert({"day_name": day, "meal_name": new_val}).execute()
            st.rerun()

st.divider()

# --- 6. SMART SHOPPING LIST (Based on Planner) ---
planned_meals = pl_df[pl_df['meal_name'].notna()]['meal_name'].tolist()

with st.expander("🛒 Smart Shopping List", expanded=True):
    if not planned_meals:
        st.info("Assign meals to the school days above to see what you need to buy!")
    else:
        needed_total = {}
        for meal in planned_meals:
            recipe_row = r_df[r_df['meal_name'] == meal]
            if not recipe_row.empty:
                raw_ings = str(recipe_row.iloc[0].get('ingredients_list', '')).split(",")
                for item in raw_ings:
                    if ":" in item:
                        name, qty = item.split(":")
                        name = name.strip().lower()
                        needed_total[name] = needed_total.get(name, 0) + int(qty.strip())
        
        shopping_output = ""
        for name, req_qty in needed_total.items():
            have_qty = pantry_dict.get(name, 0)
            if have_qty < req_qty:
                shortfall = req_qty - have_qty
                st.checkbox(f"**{name.title()}**: Buy {shortfall} (Need {req_qty}, Have {have_qty})", key=f"shop_{name}")
                shopping_output += f"- {name.title()}: {shortfall}\n"
        
        if not shopping_output:
            st.success("✅ You have everything needed for this week's planned menu!")
        else:
            st.caption("Copy for Viber/Notes:")
            st.code(shopping_output, language="text")

# --- 7. MAIN UI TABS ---
picky_mode = st.toggle("Picky Eater Mode (Kids Friendly)", value=True)

if r_df.empty:
    st.info("No recipes found in Supabase.")
else:
    r_df['rank'] = r_df.apply(lambda x: 0 if str(x.get('meal_name', '')).lower().strip() in recent_meals else (2 if x.get('favorite', False) else 1), axis=1)
    sorted_recipes = r_df.sort_values(['rank', 'meal_name'], ascending=[False, True])

    ready_to_cook = []
    missing_ingredients = []

    for _, row in sorted_recipes.iterrows():
        meal_name = str(row.get('meal_name', 'Unknown'))
        is_picky = str(row.get('picky_friendly', 'false')).lower() == 'true'
        if picky_mode and not is_picky: continue
        
        raw_ings = str(row.get('ingredients_list', '')).split(",")
        parsed_ings = []
        can_cook = True
        
        for item in raw_ings:
            if ":" in item:
                n_p, q_p = item.split(":")
                n = n_p.strip()
                try:
                    rq = int(q_p.strip())
                    aq = pantry_dict.get(n.lower(), 0)
                    has_enough = aq >= rq
                    if not has_enough: can_cook = False
                    parsed_ings.append({"display": f"{n}: {rq} (Have: {aq})", "status": "✅" if has_enough else "❌"})
                except: can_cook = False
        
        m_data = {"row": row, "parsed_ings": parsed_ings, "meal_name": meal_name}
        if can_cook: ready_to_cook.append(m_data)
        else: missing_ingredients.append(m_data)

    tab1, tab2 = st.tabs([f"✅ Ready to Cook ({len(ready_to_cook)})", f"🛒 Other Recipes ({len(missing_ingredients)})"])

    with tab1:
        if not ready_to_cook:
            st.warning("Nothing ready. Update pantry or check the next tab!")
        else:
            cols = st.columns(2)
            for i, meal in enumerate(ready_to_cook):
                m_n = meal['meal_name']
                s_key = f"ready_btn_{i}_{m_n.replace(' ', '_').lower()}"
                with cols[i % 2].expander(f"🍲 {m_n}"):
                    for ing in meal['parsed_ings']: st.write(f"{ing['status']} {ing['display']}")
                    if st.button(f"Cook {m_n}", key=s_key):
                        for item in str(meal['row']['ingredients_list']).split(","):
                            if ":" in item:
                                n, q = item.split(":")
                                n = n.strip()
                                nv = pantry_dict.get(n.lower(), 0) - int(q.strip())
                                supabase.table("pantry").update({"amount": nv}).eq("ingredient", n).execute()
                        supabase.table("history").insert({"meal_name": m_n, "date_cooked": datetime.now().strftime("%Y-%m-%d")}).execute()
                        st.balloons()
                        st.rerun()

    with tab2:
        cols = st.columns(2)
        for i, meal in enumerate(missing_ingredients):
            m_n = meal['meal_name']
            s_key_m = f"missing_btn_{i}_{m_n.replace(' ', '_').lower()}"
            with cols[i % 2].expander(f"❌ {m_n}"):
                for ing in meal['parsed_ings']: st.write(f"{ing['status']} {ing['display']}")
                st.button(f"Insufficient Stock", key=s_key_m, disabled=True)

