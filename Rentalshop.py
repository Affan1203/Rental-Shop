import streamlit as st
import pandas as pd
from datetime import datetime, date
import hashlib
import base64
from sqlalchemy import text
import pytz

# --- CONFIGURATION ---
st.set_page_config(page_title="Star Arts Admin", page_icon="📸", layout="wide")
SHOP_NAME = "Star Arts and Multiservices"
CURRENCY = "Rs."
IST = pytz.timezone('Asia/Kolkata')
DB_LIMIT_MB = 512.0

# --- DATABASE CONNECTION ---
conn = st.connection("postgresql", type="sql")

# --- SPEED OPTIMIZATION: CACHED INVENTORY ---
@st.cache_data(ttl=60)
def get_cached_inventory():
    return conn.query("SELECT * FROM inventory", ttl=0)

# --- HELPERS ---
def get_now_ist(): 
    return datetime.now(IST)

def safe_b64_decode(img_str):
    if not img_str or not isinstance(img_str, str) or img_str.strip() in ["", "None"]: 
        return None
    try: 
        return base64.b64decode(img_str)
    except: 
        return None

def make_hashes(password): 
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text): 
    return hashlib.sha256(str.encode(password)).hexdigest() == hashed_text

def get_storage_usage():
    res = conn.query("SELECT SUM(OCTET_LENGTH(customer_photo)) as bytes FROM rentals", ttl=0)
    total_bytes = res.iloc[0]['bytes'] if not res.empty and res.iloc[0]['bytes'] else 0
    return total_bytes / (1024 * 1024)

# --- AUTHENTICATION ---
if 'logged_in' not in st.session_state: 
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.title(f"🔐 {SHOP_NAME}")
    col_l, col_m, col_r = st.columns([1,2,1])
    with col_m:
        with st.container(border=True):
            auth_choice = st.radio("Access Portal", ["Login", "Create Account"], horizontal=True)
            u_input = st.text_input("Username")
            p_input = st.text_input("Password", type="password")
            if st.button("🚀 Access System", use_container_width=True, type="primary"):
                if auth_choice == "Login":
                    res = conn.query(f"SELECT password FROM users WHERE username = '{u_input}'", ttl=0)
                    if not res.empty and check_hashes(p_input, res.iloc[0]['password']):
                        st.session_state['logged_in'] = True
                        st.rerun()
                    else: st.error("Invalid Login Credentials")
                else:
                    with conn.session as session:
                        session.execute(text("INSERT INTO users (username, password) VALUES (:u, :p)"), {"u": u_input, "p": make_hashes(p_input)})
                        session.commit()
                        st.success("Account created! You can now Login.")
else:
    # --- SIDEBAR ---
    st.sidebar.title("🛠️ ADMIN PANEL")
    used_mb = get_storage_usage()
    st.sidebar.progress(min(used_mb / DB_LIMIT_MB, 1.0))
    st.sidebar.caption(f"**Storage:** {used_mb:.2f} MB / {DB_LIMIT_MB} MB")
    
    if st.sidebar.button("🔄 Clear Cache & Sync"): 
        st.cache_data.clear()
        st.rerun()
    
    if st.sidebar.button("🚪 Logout", use_container_width=True): 
        st.session_state['logged_in'] = False
        st.rerun()

    # --- MAIN UI ---
    st.title(f"📸 {SHOP_NAME}")
    tab_dash, tab_inv, tab_rev, tab_hist = st.tabs(["🚀 Dashboard", "📦 Inventory", "💰 Finance", "📜 History"])

    with tab_dash:
        st.subheader("New Rental Entry")
        items_df = get_cached_inventory()
        items_df['available'] = items_df['total_qty'] - items_df['rented_qty']
        available_options = ["-- Select Item --"] + items_df[items_df['available'] > 0]['name'].tolist()

        with st.container(border=True):
            cust_tab_new, cust_tab_ext = st.tabs(["🆕 New Customer", "⭐ Returning Customer"])
            c_name, c_phone, encoded_img = "", "", None

            with cust_tab_new:
                col_n, col_p = st.columns(2)
                c_name = col_n.text_input("Name *", key="n_new_field")
                c_phone = col_p.text_input("Phone *", key="p_new_field")
                pm = st.radio("Identity Capture", ["No Photo", "Camera", "Upload"], horizontal=True)
                if pm == "Camera":
                    img = st.camera_input("Snap Identity")
                    if img: encoded_img = base64.b64encode(img.getvalue()).decode()
                elif pm == "Upload":
                    img = st.file_uploader("Upload Identity", type=['png', 'jpg', 'jpeg'])
                    if img: encoded_img = base64.b64encode(img.getvalue()).decode()

            with cust_tab_ext:
                past_custs = conn.query("SELECT DISTINCT ON (customer_name, customer_phone) customer_name, customer_phone, id FROM rentals ORDER BY customer_name, customer_phone, id DESC", ttl=0)
                if not past_custs.empty:
                    cust_list = [f"{r['customer_name']} ({r['customer_phone']})" for _, r in past_custs.iterrows()]
                    sel = st.selectbox("Search Records", ["-- Select Customer --"] + cust_list)
                    if sel != "-- Select Customer --":
                        idx = cust_list.index(sel)
                        c_name = past_custs.iloc[idx]['customer_name']
                        c_phone = past_custs.iloc[idx]['customer_phone']
                        # Fetch photo on demand for speed
                        p_res = conn.query(f"SELECT customer_photo FROM rentals WHERE id = {past_custs.iloc[idx]['id']}", ttl=0)
                        encoded_img = p_res.iloc[0]['customer_photo']
                        ib = safe_b64_decode(encoded_img)
                        if ib: st.image(ib, width=150)
                else: st.info("No past customer data found.")

            st.divider()
            col_item, col_dep = st.columns(2)
            si = col_item.selectbox("Equipment *", available_options)
            dep = col_dep.number_input(f"Deposit ({CURRENCY})", min_value=0.0)
            pp = st.checkbox("Fully Paid / Prepaid")

            if st.button("🚀 Finalize Rental", use_container_width=True, type="primary"):
                if si != "-- Select Item --" and c_name and c_phone:
                    item_id = int(items_df[items_df['name'] == si]['id'].values[0])
                    now_str = get_now_ist().strftime("%Y-%m-%d %I:%M %p")
                    with conn.session as session:
                        session.execute(text('''INSERT INTO rentals (item_id, customer_name, customer_phone, start_time, status, deposit, is_paid, customer_photo) 
                                     VALUES (:i, :cn, :cp, :st, 'Active', :d, :ip, :ph)'''), 
                                     {"i": item_id, "cn": c_name, "cp": c_phone, "st": now_str, "d": dep, "ip": 1 if pp else 0, "ph": encoded_img})
                        session.execute(text("UPDATE inventory SET rented_qty = rented_qty + 1 WHERE id = :i"), {"i": item_id})
                        session.commit()
                        st.cache_data.clear()
                        st.rerun()
                else: st.error("Please fill Name, Phone, and Equipment.")

        st.subheader("⏳ Active Rentals")
        active = conn.query("SELECT r.*, i.name, i.rate FROM rentals r JOIN inventory i ON r.item_id = i.id WHERE r.status='Active' ORDER BY r.id DESC", ttl=0)
        for _, row in active.iterrows():
            with st.container(border=True):
                c_i, c_t, c_b = st.columns([1, 3, 1.5])
                ib = safe_b64_decode(row['customer_photo'])
                if ib: c_i.image(ib, width=80)
                c_t.markdown(f"**{row['name']}** | {row['customer_name']}")
                c_t.caption(f"📞 {row['customer_phone']} | 📅 {row['start_time']}")
                if c_b.button("✅ Return", key=f"ret_{row['id']}", use_container_width=True):
                    now = get_now_ist()
                    try: start = IST.localize(datetime.strptime(row['start_time'], "%Y-%m-%d %I:%M %p"))
                    except: start = now
                    days = max(1, (now - start).days + (1 if (now - start).seconds > 60 else 0))
                    total = days * row['rate']
                    with conn.session as session:
                        session.execute(text("UPDATE rentals SET status='Closed', total_bill=:t, return_time=:rt WHERE id=:id"), {"t": total, "rt": now.strftime("%Y-%m-%d %I:%M %p"), "id": int(row['id'])})
                        session.execute(text("UPDATE inventory SET rented_qty = rented_qty - 1 WHERE id=:i"), {"i": int(row['item_id'])})
                        session.commit()
                        st.cache_data.clear()
                        st.rerun()

    with tab_inv:
        st.subheader("Inventory Stock")
        with st.expander("➕ Add New Equipment"):
            col_n, col_r, col_q = st.columns(3)
            ni = col_n.text_input("Item Name")
            ri = col_r.number_input("Rate", min_value=0.0)
            qi = col_q.number_input("Stock", min_value=1)
            if st.button("Save Item"):
                with conn.session as session:
                    session.execute(text("INSERT INTO inventory (name, rate, total_qty, rented_qty) VALUES (:n, :r, :q, 0)"), {"n": ni, "r": ri, "q": qi})
                    session.commit()
                    st.cache_data.clear()
                    st.rerun()
        st.dataframe(get_cached_inventory(), use_container_width=True)

    with tab_rev:
        st.subheader("Finance Tracking")
        hist_rev = conn.query("SELECT total_bill, start_time FROM rentals WHERE status='Closed'", ttl=0)
        if not hist_rev.empty:
            m1, m2 = st.columns(2)
            m1.metric("Total Revenue", f"{CURRENCY} {hist_rev['total_bill'].sum():,.0f}")
            m2.metric("Orders Completed", len(hist_rev))
        else: st.info("No closed transactions yet.")

    with tab_hist:
        st.subheader("Rental Logs & Cleanup")
        # Fetch metadata only for logs
        full_hist = conn.query("SELECT id, customer_name, customer_phone, total_bill, start_time, return_time FROM rentals WHERE status='Closed' ORDER BY id DESC LIMIT 50", ttl=0)
        
        bulk_mode = st.toggle("🛠️ Bulk Delete Mode")
        if bulk_mode:
            sel_all = st.checkbox("✅ Select All Visible", key="master_del_check")
            to_del = []
            for _, r in full_hist.iterrows():
                chk = st.checkbox(f"{r['customer_name']} | {r['start_time'][:10]}", key=f"d_{r['id']}", value=sel_all)
                if chk: to_del.append(int(r['id']))
            if to_del and st.button(f"🔥 Delete {len(to_del)} Records", type="primary"):
                with conn.session as session:
                    session.execute(text("DELETE FROM rentals WHERE id IN :ids"), {"ids": tuple(to_del)})
                    session.commit()
                    st.rerun()
        else:
            q_search = st.text_input("🔍 Search History")
            if q_search:
                full_hist = full_hist[full_hist.apply(lambda r: q_search.lower() in str(r['customer_name']).lower() or q_search in str(r['customer_phone']), axis=1)]
            for _, row in full_hist.iterrows():
                with st.expander(f"📄 {row['customer_name']} | {CURRENCY}{row['total_bill']}"):
                    # Fetch photo on expand
                    p_res = conn.query(f"SELECT customer_photo FROM rentals WHERE id = {row['id']}", ttl=0)
                    ib = safe_b64_decode(p_res.iloc[0]['customer_photo'])
                    c_img, c_det = st.columns([1, 3])
                    if ib: c_img.image(ib, width=120)
                    c_det.write(f"📞 {row['customer_phone']}\n🕒 {row['start_time']} to {row['return_time']}")

    st.caption(f"© 2026 {SHOP_NAME} | Premium Admin Dashboard")
