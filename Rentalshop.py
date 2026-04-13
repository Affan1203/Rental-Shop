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
    .stApp { background-color: #f4f7f9; }
    .main-header {
        font-size: 2.2rem;
        color: #1e3a8a;
        font-weight: 800;
        text-align: center;
        padding: 10px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        background-color: #ffffff;
        border-radius: 10px 10px 0px 0px;
        gap: 5px;
        padding: 10px;
    }
    .stTabs [aria-selected="true"] { background-color: #1e3a8a !important; color: white !important; }
    div[data-testid="stMetricValue"] { color: #1e3a8a; font-weight: 700; }
    .footer { text-align: center; color: #64748b; font-size: 0.8rem; margin-top: 50px; }
</style>
""", unsafe_markdown=True)

# --- DATABASE CONNECTION ---
conn = st.connection("postgresql", type="sql")

# --- INITIALIZE TABLES ---
with conn.session as session:
    session.execute(text('''CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username TEXT, password TEXT)'''))
    session.execute(text('''CREATE TABLE IF NOT EXISTS inventory (id SERIAL PRIMARY KEY, name TEXT, rate REAL, total_qty INTEGER, rented_qty INTEGER)'''))
    session.execute(text('''CREATE TABLE IF NOT EXISTS rentals (
        id SERIAL PRIMARY KEY, item_id INTEGER, customer_name TEXT, customer_phone TEXT,
        referred_by_name TEXT, referred_by_phone TEXT, start_time TEXT, status TEXT, 
        deposit REAL, total_bill REAL, is_paid INTEGER, customer_photo TEXT, return_time TEXT)'''))
    try:
        session.execute(text("ALTER TABLE rentals ADD COLUMN IF NOT EXISTS return_time TEXT"))
    except: pass
    session.commit()

# --- HELPERS ---
def get_now_ist(): return datetime.now(IST)

def safe_b64_decode(img_str):
    if not img_str or not isinstance(img_str, str) or img_str.strip() in ["", "None"]: return None
    try: return base64.b64decode(img_str)
    except: return None

def make_hashes(password): return hashlib.sha256(str.encode(password)).hexdigest()
def check_hashes(password, hashed_text): return hashlib.sha256(str.encode(password)).hexdigest() == hashed_text

def get_storage_usage():
    res = conn.query("SELECT SUM(OCTET_LENGTH(customer_photo)) as bytes FROM rentals", ttl=0)
    total_bytes = res.iloc[0]['bytes'] if not res.empty and res.iloc[0]['bytes'] else 0
    return total_bytes / (1024 * 1024)

# --- AUTHENTICATION ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.markdown(f"<h1 class='main-header'>{SHOP_NAME}</h1>", unsafe_markdown=True)
    col_l, col_m, col_r = st.columns([1,2,1])
    with col_m:
        with st.container(border=True):
            auth_choice = st.radio("Access Portal", ["Login", "Create Account"], horizontal=True)
            u_input = st.text_input("Username")
            p_input = st.text_input("Password", type="password")
            if st.button("🚀 Access System", use_container_width=True, type="primary"):
                if auth_choice == "Create Account":
                    with conn.session as session:
                        session.execute(text("INSERT INTO users (username, password) VALUES (:u, :p)"), {"u": u_input, "p": make_hashes(p_input)})
                        session.commit(); st.success("Account created! Please Login.")
                else:
                    res = conn.query(f"SELECT password FROM users WHERE username = '{u_input}'", ttl=0)
                    if not res.empty and check_hashes(p_input, res.iloc[0]['password']):
                        st.session_state['logged_in'] = True; st.rerun()
                    else: st.error("Invalid Login")
else:
    # --- SIDEBAR ---
    st.sidebar.markdown(f"## 🛠️ ADMIN")
    st.sidebar.divider()
    st.sidebar.subheader("🗄️ Database Health")
    used_mb = get_storage_usage()
    usage_per = min(used_mb / DB_LIMIT_MB, 1.0)
    st.sidebar.progress(usage_per)
    st.sidebar.caption(f"**Used:** {used_mb:.2f} MB / {DB_LIMIT_MB} MB")
    if st.sidebar.button("🔄 Sync & Refresh"): st.rerun()
    st.sidebar.divider()
    if st.sidebar.button("🚪 Logout", use_container_width=True): 
        st.session_state['logged_in'] = False; st.rerun()

    # --- MAIN UI ---
    st.markdown(f"<h1 class='main-header'>📸 {SHOP_NAME}</h1>", unsafe_markdown=True)
    tab_dash, tab_inv, tab_rev, tab_hist = st.tabs(["🚀 Dashboard", "📦 Inventory", "💰 Finance", "📜 History"])

    with tab_dash:
        st.subheader("New Rental Entry")
        items_df = conn.query("SELECT * FROM inventory", ttl=0)
        items_df['available'] = items_df['total_qty'] - items_df['rented_qty']
        available_options = ["-- Select Item --"] + items_df[items_df['available'] > 0]['name'].tolist()

        with st.container(border=True):
            cust_tab_new, cust_tab_ext = st.tabs(["🆕 New Customer", "⭐ Returning Customer"])
            c_name, c_phone, encoded_img = "", "", None

            with cust_tab_new:
                c1, c2 = st.columns(2)
                c_name = c1.text_input("Name *", key="n_new")
                c_phone = c2.text_input("Phone *", key="p_new")
                pm = st.radio("Identity", ["No Photo", "Camera", "Upload"], horizontal=True)
                if pm == "Camera":
                    img = st.camera_input("Snap")
                    if img: encoded_img = base64.b64encode(img.getvalue()).decode()
                elif pm == "Upload":
                    img = st.file_uploader("Upload", type=['png', 'jpg', 'jpeg'])
                    if img: encoded_img = base64.b64encode(img.getvalue()).decode()

            with cust_tab_ext:
                past_custs = conn.query("SELECT DISTINCT ON (customer_name, customer_phone) customer_name, customer_phone, customer_photo FROM rentals ORDER BY customer_name, customer_phone, id DESC", ttl=0)
                if not past_custs.empty:
                    cust_list = [f"{r['customer_name']} ({r['customer_phone']})" for _, r in past_custs.iterrows()]
                    sel = st.selectbox("Search Records", ["-- Select Customer --"] + cust_list)
                    if sel != "-- Select Customer --":
                        idx = cust_list.index(sel)
                        c_name = past_custs.iloc[idx]['customer_name']
                        c_phone = past_custs.iloc[idx]['customer_phone']
                        encoded_img = past_custs.iloc[idx]['customer_photo']
                        st.info(f"Identity Loaded: {c_name}")
                        ib = safe_b64_decode(encoded_img)
                        if ib: st.image(ib, width=120)
                else: st.info("No records found.")

            st.divider()
            col_x, col_y = st.columns(2)
            si = col_x.selectbox("Item *", available_options)
            dep = col_y.number_input(f"Deposit ({CURRENCY})", min_value=0.0)
            pp = st.checkbox("Mark as Fully Paid")

            if st.button("🚀 Start Rental Transaction", use_container_width=True, type="primary"):
                if si != "-- Select Item --" and c_name and c_phone:
                    item_id = int(items_df[items_df['name'] == si]['id'].values[0])
                    now_str = get_now_ist().strftime("%Y-%m-%d %I:%M %p")
                    with conn.session as session:
                        session.execute(text('''INSERT INTO rentals (item_id, customer_name, customer_phone, start_time, status, deposit, is_paid, customer_photo) 
                                     VALUES (:i, :cn, :cp, :st, 'Active', :d, :ip, :ph)'''), 
                                     {"i": item_id, "cn": c_name, "cp": c_phone, "st": now_str, "d": dep, "ip": 1 if pp else 0, "ph": encoded_img})
                        session.execute(text("UPDATE inventory SET rented_qty = rented_qty + 1 WHERE id = :i"), {"i": item_id})
                        session.commit(); st.success("Transaction Successful!"); st.rerun()
                else: st.error("Please fill Name, Phone, and Item.")

        st.subheader("⏳ Live Sessions")
        active = conn.query("SELECT r.*, i.name, i.rate FROM rentals r JOIN inventory i ON r.item_id = i.id WHERE r.status='Active' ORDER BY r.id DESC", ttl=0)
        for _, row in active.iterrows():
            with st.container(border=True):
                col_i, col_t, col_b = st.columns([1, 3, 1.5])
                ib = safe_b64_decode(row['customer_photo'])
                if ib: col_i.image(ib, width=80)
                col_t.markdown(f"**{row['name']}** | {row['customer_name']}")
                if col_b.button("✅ End Rental", key=f"ret_{row['id']}", use_container_width=True):
                    now = get_now_ist()
                    try: start = IST.localize(datetime.strptime(row['start_time'], "%Y-%m-%d %I:%M %p"))
                    except: start = now
                    days = max(1, (now - start).days + (1 if (now - start).seconds > 60 else 0))
                    total = days * row['rate']
                    with conn.session as session:
                        session.execute(text("UPDATE rentals SET status='Closed', total_bill=:t, return_time=:rt WHERE id=:id"), {"t": total, "rt": now.strftime("%Y-%m-%d %I:%M %p"), "id": int(row['id'])})
                        session.execute(text("UPDATE inventory SET rented_qty = rented_qty - 1 WHERE id=:i"), {"i": int(row['item_id'])})
                        session.commit(); st.rerun()

    with tab_inv:
        st.subheader("Stock Management")
        with st.expander("➕ Add New Inventory"):
            c1, c2, c3 = st.columns(3)
            ni, ri, qi = c1.text_input("Item Name"), c2.number_input("Rate", min_value=0.0), c3.number_input("Stock", min_value=1)
            if st.button("Save Item", type="primary"):
                with conn.session as session:
                    session.execute(text("INSERT INTO inventory (name, rate, total_qty, rented_qty) VALUES (:n, :r, :q, 0)"), {"n": ni, "r": ri, "q": qi})
                    session.commit(); st.rerun()
        st.dataframe(conn.query("SELECT name as \"Item\", rate as \"Rate\", total_qty as \"Total\", rented_qty as \"Rented\" FROM inventory", ttl=0), use_container_width=True)

    with tab_rev:
        st.subheader("Revenue Tracker")
        hist = conn.query("SELECT * FROM rentals WHERE status='Closed'", ttl=0)
        if not hist.empty:
            hist['date_obj'] = pd.to_datetime(hist['start_time'], errors='coerce').dt.date
            today = get_now_ist().date()
            m1, m2 = st.columns(2)
            m1.metric("Today's Revenue", f"{CURRENCY} {hist[hist['date_obj'] == today]['total_bill'].sum():,.0f}")
            m2.metric("Total Billable", f"{CURRENCY} {hist['total_bill'].sum():,.0f}")
        else: st.info("No data.")

    with tab_hist:
        st.subheader("Transaction Logs")
        full_hist = conn.query("SELECT * FROM rentals WHERE status='Closed' ORDER BY id DESC", ttl=0)
        bulk_mode = st.toggle("🛠️ Enable Bulk Delete Mode")
        
        if bulk_mode:
            if not full_hist.empty:
                # FIXED BULK DELETE LOGIC
                select_all = st.checkbox("✅ Select All Records", key="master_del")
                to_delete = []
                st.divider()
                for _, row in full_hist.iterrows():
                    is_checked = st.checkbox(f"{row['customer_name']} | {row['start_time'][:10]}", key=f"del_{row['id']}", value=select_all)
                    if is_checked: to_delete.append(int(row['id']))
                if to_delete and st.button(f"🔥 Permanently Delete {len(to_delete)} Records", type="primary", use_container_width=True):
                    with conn.session as session:
                        session.execute(text("DELETE FROM rentals WHERE id IN :ids"), {"ids": tuple(to_delete)})
                        session.commit(); st.success("Records Deleted"); st.rerun()
            else: st.info("No records.")
        else:
            q = st.text_input("🔍 Search History")
            if q: full_hist = full_hist[full_hist.apply(lambda r: q.lower() in str(r['customer_name']).lower() or q in str(r['customer_phone']), axis=1)]
            for _, row in full_hist.iterrows():
                with st.expander(f"📄 {row['customer_name']} | {CURRENCY}{row['total_bill']}"):
                    c1, c2 = st.columns([1, 3])
                    ib = safe_b64_decode(row['customer_photo'])
                    if ib: c1.image(ib, width=120)
                    c2.write(f"📞 {row['customer_phone']} | 🕒 {row['start_time']} to {row['return_time']}")

    st.markdown("<div class='footer'>© 2026 Star Arts and Multiservices</div>", unsafe_markdown=True)
