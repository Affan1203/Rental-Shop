import streamlit as st
import pandas as pd
from datetime import datetime, date
import hashlib
import base64
from sqlalchemy import text
import pytz

# --- CONFIGURATION ---
SHOP_NAME = "Star Arts and Multiservices"
CURRENCY = "Rs."
IST = pytz.timezone('Asia/Kolkata')
DB_LIMIT_MB = 512.0

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

# --- AUTH ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.title(f"🔐 {SHOP_NAME}")
    auth_choice = st.radio("Portal", ["Login", "Create Account"])
    u_input, p_input = st.text_input("Username"), st.text_input("Password", type="password")
    if st.button("Proceed"):
        if auth_choice == "Create Account":
            with conn.session as session:
                session.execute(text("INSERT INTO users (username, password) VALUES (:u, :p)"), {"u": u_input, "p": make_hashes(p_input)})
                session.commit(); st.success("Account created!")
        else:
            res = conn.query(f"SELECT password FROM users WHERE username = '{u_input}'", ttl=0)
            if not res.empty and check_hashes(p_input, res.iloc[0]['password']):
                st.session_state['logged_in'] = True; st.rerun()
            else: st.error("Invalid Login")
else:
    # --- SIDEBAR STORAGE MONITOR ---
    st.sidebar.title(f"🛠️ {SHOP_NAME}")
    st.sidebar.divider()
    st.sidebar.subheader("🗄️ Database Storage")
    used_mb = get_storage_usage()
    usage_per = min(used_mb / DB_LIMIT_MB, 1.0)
    
    if usage_per > 0.9: st.sidebar.error("⚠️ Storage almost FULL!")
    elif usage_per > 0.7: st.sidebar.warning("Storage filling up...")
    
    st.sidebar.progress(usage_per)
    st.sidebar.caption(f"Used: {used_mb:.2f} MB / {DB_LIMIT_MB} MB")
    if st.sidebar.button("🔄 Refresh Storage"): st.rerun()
    st.sidebar.divider()
    if st.sidebar.button("Logout"): 
        st.session_state['logged_in'] = False
        st.rerun()

    tab_dash, tab_inv, tab_rev, tab_hist = st.tabs(["🚀 Dashboard", "📦 Inventory", "💰 Reports", "📜 History"])

    with tab_dash:
        st.header("New Rental")
        items_df = conn.query("SELECT * FROM inventory", ttl=0)
        items_df['available'] = items_df['total_qty'] - items_df['rented_qty']
        available_options = ["-- Select Item --"] + items_df[items_df['available'] > 0]['name'].tolist()

        # CUSTOMER ENTRY TABS
        cust_tab_new, cust_tab_ext = st.tabs(["🆕 New Customer", "⭐ Existing Customer"])
        c_name, c_phone, encoded_img = "", "", None

        with cust_tab_new:
            col1, col2 = st.columns(2)
            c_name = col1.text_input("Full Name *", key="n_new")
            c_phone = col2.text_input("Phone Number *", key="p_new")
            pm = st.radio("Photo", ["No Photo", "Take Photo", "Upload"], horizontal=True)
            if pm == "Take Photo":
                img = st.camera_input("Capture")
                if img: encoded_img = base64.b64encode(img.getvalue()).decode()
            elif pm == "Upload":
                img = st.file_uploader("Upload", type=['png', 'jpg', 'jpeg'])
                if img: encoded_img = base64.b64encode(img.getvalue()).decode()

        with cust_tab_ext:
            # Query unique customers
            past_custs = conn.query("SELECT DISTINCT ON (customer_name, customer_phone) customer_name, customer_phone, customer_photo FROM rentals ORDER BY customer_name, customer_phone, id DESC", ttl=0)
            if not past_custs.empty:
                cust_list = [f"{r['customer_name']} ({r['customer_phone']})" for _, r in past_custs.iterrows()]
                sel = st.selectbox("Search Past Customers", ["-- Select --"] + cust_list)
                if sel != "-- Select --":
                    idx = cust_list.index(sel)
                    c_name, c_phone = past_custs.iloc[idx]['customer_name'], past_custs.iloc[idx]['customer_phone']
                    encoded_img = past_custs.iloc[idx]['customer_photo']
                    st.success(f"Autofilled: {c_name}")
                    ib = safe_b64_decode(encoded_img)
                    if ib: st.image(ib, width=150, caption="Stored Photo")
            else: st.info("No records found yet.")

        st.divider()
        si = st.selectbox("Select Item *", available_options)
        r1, r2 = st.columns(2)
        rn, rp = r1.text_input("Referred By"), r2.text_input("Referral Phone")
        dep, pp = st.number_input(f"Deposit ({CURRENCY})", min_value=0.0), st.checkbox("Fully Paid / Prepaid")

        if st.button("🚀 Start Rental", use_container_width=True):
            if si != "-- Select Item --" and c_name and c_phone:
                item_id = int(items_df[items_df['name'] == si]['id'].values[0])
                now_str = get_now_ist().strftime("%Y-%m-%d %I:%M %p")
                with conn.session as session:
                    session.execute(text('''INSERT INTO rentals (item_id, customer_name, customer_phone, referred_by_name, referred_by_phone, start_time, status, deposit, is_paid, customer_photo) 
                                 VALUES (:i, :cn, :cp, :rn, :rp, :st, 'Active', :d, :ip, :ph)'''), 
                                 {"i": item_id, "cn": c_name, "cp": c_phone, "rn": rn, "rp": rp, "st": now_str, "d": dep, "ip": 1 if pp else 0, "ph": encoded_img})
                    session.execute(text("UPDATE inventory SET rented_qty = rented_qty + 1 WHERE id = :i"), {"i": item_id})
                    session.commit(); st.rerun()
            else: st.error("Please fill required fields.")

        st.divider()
        st.header("⏳ Active Sessions (IST)")
        active = conn.query("SELECT r.*, i.name, i.rate FROM rentals r JOIN inventory i ON r.item_id = i.id WHERE r.status='Active'", ttl=0)
        for _, row in active.iterrows():
            with st.container(border=True):
                col_a, col_b = st.columns([1, 3])
                ib = safe_b64_decode(row['customer_photo'])
                if ib: col_a.image(ib, width=100)
                col_b.write(f"**{row['name']}** -> {row['customer_name']}")
                if col_b.button("✅ Return Item", key=f"ret_{row['id']}", use_container_width=True):
                    now = get_now_ist()
                    try: start = IST.localize(datetime.strptime(row['start_time'], "%Y-%m-%d %I:%M %p"))
                    except: start = now
                    diff = now - start
                    days = max(1, diff.days + (1 if diff.seconds > 60 else 0))
                    total = days * row['rate']
                    with conn.session as session:
                        session.execute(text("UPDATE rentals SET status='Closed', total_bill=:t, return_time=:rt WHERE id=:id"), {"t": total, "rt": now.strftime("%Y-%m-%d %I:%M %p"), "id": int(row['id'])})
                        session.execute(text("UPDATE inventory SET rented_qty = rented_qty - 1 WHERE id=:i"), {"i": int(row['item_id'])})
                        session.commit(); st.rerun()

    with tab_inv:
        st.header("Inventory")
        with st.expander("➕ Add New Item"):
            cx, cy, cz = st.columns(3)
            n, r, q = cx.text_input("Name"), cy.number_input("Rate"), cz.number_input("Stock", min_value=1)
            if st.button("Save Item"):
                with conn.session as session:
                    session.execute(text("INSERT INTO inventory (name, rate, total_qty, rented_qty) VALUES (:n, :r, :q, 0)"), {"n": n, "r": r, "q": q})
                    session.commit(); st.rerun()
        st.dataframe(conn.query("SELECT name, rate, total_qty, rented_qty FROM inventory", ttl=0), use_container_width=True)

    with tab_rev:
        st.header("📊 Revenue Reports")
        hist = conn.query("SELECT * FROM rentals WHERE status='Closed'", ttl=0)
        if not hist.empty:
            hist['date_obj'] = pd.to_datetime(hist['start_time'], errors='coerce').dt.date
            f = st.radio("Period", ["Today", "Month", "Custom"], horizontal=True)
            today = get_now_ist().date()
            if f == "Today": s_f = e_f = today
            elif f == "Month": s_f, e_f = today.replace(day=1), today
            else: s_f, e_f = st.columns(2)[0].date_input("From", today), st.columns(2)[1].date_input("To", today)
            f_df = hist[(hist['date_obj'] >= s_f) & (hist['date_obj'] <= e_f)]
            st.metric("Total Revenue", f"{CURRENCY} {f_df['total_bill'].sum():,.2f}")

    with tab_hist:
        st.header("📜 History & Cleanup")
        full_hist = conn.query("SELECT * FROM rentals WHERE status='Closed' ORDER BY id DESC", ttl=0)
        
        cleanup_mode = st.toggle("🛠️ Enable Bulk Delete Mode")
        
        if cleanup_mode:
            if full_hist.empty: st.info("No history to delete.")
            else:
                st.warning("Deletions are permanent.")
                select_all = st.checkbox("✅ Select All Records")
                to_delete = []
                for _, row in full_hist.iterrows():
                    chk = st.checkbox(f"{row['customer_name']} | {row['start_time'][:10]} | {CURRENCY}{row['total_bill']}", key=f"bulk_{row['id']}", value=select_all)
                    if chk: to_delete.append(int(row['id']))
                
                if to_delete:
                    if st.button(f"🔥 Delete {len(to_delete)} Records", type="primary", use_container_width=True):
                        with conn.session as session:
                            session.execute(text("DELETE FROM rentals WHERE id IN :ids"), {"ids": tuple(to_delete)})
                            session.commit(); st.rerun()
        else:
            search = st.text_input("🔍 Search Name/Phone").lower()
            if search:
                full_hist = full_hist[full_hist.apply(lambda r: search in str(r['customer_name']).lower() or search in str(r['customer_phone']), axis=1)]
            for _, row in full_hist.iterrows():
                with st.expander(f"{row['customer_name']} | {CURRENCY}{row['total_bill']}"):
                    c1, c2 = st.columns([1, 3])
                    ib = safe_b64_decode(row['customer_photo'])
                    if ib: c1.image(ib, width=150)
                    c2.write(f"**🕒 Rented:** {row['start_time']}\n**🕒 Returned:** {row['return_time']}\n**📞 Phone:** {row['customer_phone']}")
