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

# --- CUSTOM CSS (FIXED INDENTATION) ---
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
        background-attachment: fixed;
    }
    .stApp, p, label, .stMarkdown {
        color: #f8fafc !important;
    }
    div[data-testid="stVerticalBlock"] > div > div[data-testid="stVerticalBlock"] {
        background-color: rgba(255, 255, 255, 0.05);
        padding: 20px;
        border-radius: 15px;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    .main-header {
        font-size: 2.5rem;
        color: #38bdf8;
        font-weight: 800;
        text-align: center;
        padding: 20px;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    .stTabs [data-baseweb="tab-list"] { background-color: transparent; }
    .stTabs [data-baseweb="tab"] { color: #94a3b8; font-weight: 600; }
    .stTabs [aria-selected="true"] { color: #38bdf8 !important; border-bottom-color: #38bdf8 !important; }
    section[data-testid="stSidebar"] { background-color: rgba(15, 23, 42, 0.95) !important; }
</style>
""", unsafe_markdown=True)

# --- PERSISTENT SESSION ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_name' not in st.session_state: st.session_state.user_name = ""

# --- DATABASE CONNECTION ---
conn = st.connection("postgresql", type="sql")

# --- HELPERS ---
@st.cache_data(ttl=300)
def get_cached_inventory():
    return conn.query("SELECT * FROM inventory", ttl=0)

def get_now_ist(): return datetime.now(IST)

def safe_b64_decode(img_str):
    if not img_str or not isinstance(img_str, str) or img_str.strip() in ["", "None"]: return None
    try: return base64.b64decode(img_str)
    except: return None

def make_hashes(p): return hashlib.sha256(str.encode(p)).hexdigest()
def check_hashes(p, h): return hashlib.sha256(str.encode(p)).hexdigest() == h

def get_storage_usage():
    try:
        res = conn.query("SELECT SUM(OCTET_LENGTH(customer_photo)) as bytes FROM rentals", ttl=0)
        total_bytes = res.iloc[0]['bytes'] if not res.empty and res.iloc[0]['bytes'] else 0
        return total_bytes / (1024 * 1024)
    except: return 0.0

# --- UI LOGIC ---
if not st.session_state.logged_in:
    st.markdown(f"<h1 class='main-header'>🔐 {SHOP_NAME}</h1>", unsafe_markdown=True)
    col_l, col_m, col_r = st.columns([1,2,1])
    with col_m:
        with st.container():
            auth_choice = st.radio("Access Portal", ["Login", "Create Account"], horizontal=True)
            u_input = st.text_input("Username")
            p_input = st.text_input("Password", type="password")
            if st.button("🚀 Access System", use_container_width=True, type="primary"):
                if auth_choice == "Login":
                    res = conn.query(f"SELECT password FROM users WHERE username = '{u_input}'", ttl=0)
                    if not res.empty and check_hashes(p_input, res.iloc[0]['password']):
                        st.session_state.logged_in, st.session_state.user_name = True, u_input
                        st.rerun()
                    else: st.error("Invalid Credentials")
                else:
                    with conn.session as session:
                        session.execute(text("INSERT INTO users (username, password) VALUES (:u, :p)"), {"u": u_input, "p": make_hashes(p_input)})
                        session.commit(); st.success("Account created!")
else:
    # --- SIDEBAR ---
    st.sidebar.markdown(f"## 👋 {st.session_state.user_name}")
    used_mb = get_storage_usage()
    st.sidebar.subheader("🗄️ Storage")
    st.sidebar.progress(min(used_mb / DB_LIMIT_MB, 1.0))
    st.sidebar.caption(f"{used_mb:.2f} MB / {DB_LIMIT_MB} MB")
    if st.sidebar.button("🔄 Sync"): st.cache_data.clear(); st.rerun()
    st.sidebar.divider()
    if st.sidebar.button("🚪 Logout", use_container_width=True): 
        st.session_state.logged_in, st.session_state.user_name = False, ""; st.rerun()

    # --- MAIN CONTENT ---
    st.markdown(f"<h1 class='main-header'>📸 {SHOP_NAME}</h1>", unsafe_markdown=True)
    tab_dash, tab_inv, tab_rev, tab_hist = st.tabs(["🚀 Dashboard", "📦 Inventory", "💰 Finance", "📜 History"])

    with tab_dash:
        items_df = get_cached_inventory()
        items_df['available'] = items_df['total_qty'] - items_df['rented_qty']
        available_options = ["-- Select Item --"] + items_df[items_df['available'] > 0]['name'].tolist()

        with st.container():
            cust_tab_new, cust_tab_ext = st.tabs(["🆕 New Customer", "⭐ Returning"])
            c_name, c_phone, encoded_img = "", "", None

            with cust_tab_new:
                cn, cp = st.columns(2)
                c_name, c_phone = cn.text_input("Name *", key="n_n"), cp.text_input("Phone *", key="p_n")
                pm = st.radio("Identity", ["No Photo", "Camera", "Upload"], horizontal=True)
                if pm == "Camera":
                    img = st.camera_input("Snap")
                    if img: encoded_img = base64.b64encode(img.getvalue()).decode()
                elif pm == "Upload":
                    img = st.file_uploader("Upload", type=['png','jpg','jpeg'])
                    if img: encoded_img = base64.b64encode(img.getvalue()).decode()

            with cust_tab_ext:
                past = conn.query("SELECT DISTINCT ON (customer_name, customer_phone) customer_name, customer_phone, id FROM rentals ORDER BY customer_name, customer_phone, id DESC", ttl=0)
                if not past.empty:
                    cust_list = [f"{r['customer_name']} ({r['customer_phone']})" for _, r in past.iterrows()]
                    sel = st.selectbox("Search Records", ["-- Select Customer --"] + cust_list)
                    if sel != "-- Select Customer --":
                        idx = cust_list.index(sel)
                        c_name, c_phone = past.iloc[idx]['customer_name'], past.iloc[idx]['customer_phone']
                        p_res = conn.query(f"SELECT customer_photo FROM rentals WHERE id = {past.iloc[idx]['id']}", ttl=0)
                        encoded_img = p_res.iloc[0]['customer_photo']
                        ib = safe_b64_decode(encoded_img)
                        if ib: st.image(ib, width=150)
                else: st.info("No records.")

            st.divider()
            ci, cd = st.columns(2)
            si = ci.selectbox("Equipment *", available_options)
            dep = cd.number_input(f"Deposit ({CURRENCY})", min_value=0.0)
            pp = st.checkbox("Prepaid / Fully Paid")

            if st.button("🚀 Start Rental", use_container_width=True, type="primary"):
                if si != "-- Select Item --" and c_name and c_phone:
                    item_id = int(items_df[items_df['name'] == si]['id'].values[0])
                    now_str = get_now_ist().strftime("%Y-%m-%d %I:%M %p")
                    with conn.session as session:
                        session.execute(text('''INSERT INTO rentals (item_id, customer_name, customer_phone, start_time, status, deposit, is_paid, customer_photo) 
                                     VALUES (:i, :cn, :cp, :st, 'Active', :d, :ip, :ph)'''), 
                                     {"i": item_id, "cn": c_name, "cp": c_phone, "st": now_str, "d": dep, "ip": 1 if pp else 0, "ph": encoded_img})
                        session.execute(text("UPDATE inventory SET rented_qty = rented_qty + 1 WHERE id = :i"), {"i": item_id})
                        session.commit(); st.cache_data.clear(); st.rerun()

        st.subheader("⏳ Active Rentals")
        active = conn.query("SELECT r.*, i.name, i.rate FROM rentals r JOIN inventory i ON r.item_id = i.id WHERE r.status='Active' ORDER BY r.id DESC", ttl=0)
        for _, row in active.iterrows():
            with st.container():
                c_i, c_t, c_b = st.columns([1, 3, 1.5])
                ib = safe_b64_decode(row['customer_photo'])
                if ib: c_i.image(ib, width=80)
                c_t.markdown(f"**{row['name']}** | {row['customer_name']}")
                if c_b.button("✅ Return", key=f"ret_{row['id']}", use_container_width=True):
                    now = get_now_ist()
                    try: start = IST.localize(datetime.strptime(row['start_time'], "%Y-%m-%d %I:%M %p"))
                    except: start = now
                    days = max(1, (now - start).days + (1 if (now - start).seconds > 60 else 0))
                    with conn.session as session:
                        session.execute(text("UPDATE rentals SET status='Closed', total_bill=:t, return_time=:rt WHERE id=:id"), {"t": days * row['rate'], "rt": now.strftime("%Y-%m-%d %I:%M %p"), "id": int(row['id'])})
                        session.execute(text("UPDATE inventory SET rented_qty = rented_qty - 1 WHERE id=:i"), {"i": int(row['item_id'])})
                        session.commit(); st.cache_data.clear(); st.rerun()

    with tab_inv:
        st.subheader("Inventory Stock")
        with st.expander("➕ Add Item"):
            c1, c2, c3 = st.columns(3)
            ni, ri, qi = c1.text_input("Name"), c2.number_input("Rate"), c3.number_input("Stock", min_value=1)
            if st.button("Save"):
                with conn.session as session:
                    session.execute(text("INSERT INTO inventory (name, rate, total_qty, rented_qty) VALUES (:n, :r, :q, 0)"), {"n": ni, "r": ri, "q": qi})
                    session.commit(); st.cache_data.clear(); st.rerun()
        st.dataframe(get_cached_inventory(), use_container_width=True)

    with tab_rev:
        st.subheader("Finance")
        hist_rev = conn.query("SELECT total_bill FROM rentals WHERE status='Closed'", ttl=0)
        if not hist_rev.empty:
            m1, m2 = st.columns(2)
            m1.metric("Total Revenue", f"{CURRENCY} {hist_rev['total_bill'].sum():,.0f}")
            m2.metric("Orders", len(hist_rev))
        else: st.info("No data.")

    with tab_hist:
        st.subheader("Cleanup & Logs")
        full_hist = conn.query("SELECT id, customer_name, customer_phone, total_bill, start_time, return_time FROM rentals WHERE status='Closed' ORDER BY id DESC LIMIT 50", ttl=0)
        if st.toggle("🛠️ Bulk Delete Mode"):
            sel_all = st.checkbox("✅ Select All Visible")
            to_del = [int(r['id']) for _, r in full_hist.iterrows() if st.checkbox(f"{r['customer_name']} | {r['start_time'][:10]}", key=f"d_{r['id']}", value=sel_all)]
            if to_del and st.button(f"🔥 Delete {len(to_del)} Records", type="primary"):
                with conn.session as session:
                    session.execute(text("DELETE FROM rentals WHERE id IN :ids"), {"ids": tuple(to_del)})
                    session.commit(); st.rerun()
        else:
            for _, row in full_hist.iterrows():
                with st.expander(f"📄 {row['customer_name']} | {CURRENCY}{row['total_bill']}"):
                    p_res = conn.query(f"SELECT customer_photo FROM rentals WHERE id = {row['id']}", ttl=0)
                    ib = safe_b64_decode(p_res.iloc[0]['customer_photo'])
                    c_img, c_det = st.columns([1, 3])
                    if ib: c_img.image(ib, width=120)
                    c_det.write(f"📞 {row['customer_phone']} | 🕒 {row['start_time']}")
