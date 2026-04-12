import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import hashlib
import base64
from fpdf import FPDF
from sqlalchemy import text

# --- CONFIGURATION ---
SHOP_NAME = "Star Arts and Multiservices"
CURRENCY = "Rs."

# --- DATABASE CONNECTION (PERMANENT CLOUD) ---
conn = st.connection("postgresql", type="sql")

# --- INITIALIZE TABLES IN CLOUD ---
with conn.session as session:
    session.execute(text('''CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username TEXT, password TEXT)'''))
    session.execute(text('''CREATE TABLE IF NOT EXISTS inventory (id SERIAL PRIMARY KEY, name TEXT, rate REAL, total_qty INTEGER, rented_qty INTEGER)'''))
    session.execute(text('''CREATE TABLE IF NOT EXISTS rentals (
        id SERIAL PRIMARY KEY, item_id INTEGER, customer_name TEXT, customer_phone TEXT,
        referred_by_name TEXT, referred_by_phone TEXT, start_time TEXT, status TEXT, 
        deposit REAL, total_bill REAL, is_paid INTEGER, customer_photo TEXT)'''))
    session.commit()

# --- HELPERS ---
def generate_pdf(df, report_type):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt=SHOP_NAME, ln=True, align='C')
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Revenue Report: {report_type}", ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(45, 10, "Customer", 1); pdf.cell(35, 10, "Date", 1); pdf.cell(45, 10, "Referral", 1); pdf.cell(35, 10, f"Total ({CURRENCY})", 1); pdf.cell(30, 10, "Status", 1); pdf.ln()
    pdf.set_font("Arial", size=9)
    total_sum = 0
    for _, row in df.iterrows():
        pdf.cell(45, 10, str(row['customer_name'])[:18], 1); pdf.cell(35, 10, str(row['start_time'])[:11], 1); pdf.cell(45, 10, str(row['referred_by_name'])[:18], 1); pdf.cell(35, 10, f"{row['total_bill'] or 0}", 1); pdf.cell(30, 10, "Paid" if row['is_paid'] else "Settled", 1); pdf.ln()
        total_sum += (row['total_bill'] or 0)
    pdf.ln(5); pdf.set_font("Arial", 'B', 12); pdf.cell(200, 10, txt=f"Grand Total: {CURRENCY} {total_sum:,.2f}", ln=True, align='R')
    return pdf.output(dest='S').encode('latin-1')

def make_hashes(password): return hashlib.sha256(str.encode(password)).hexdigest()
def check_hashes(password, hashed_text): return hashlib.sha256(str.encode(password)).hexdigest() == hashed_text

# --- AUTH ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.title(f"🔐 {SHOP_NAME}")
    auth_choice = st.radio("Portal", ["Login", "Create Account"])
    u_input = st.text_input("Username")
    p_input = st.text_input("Password", type="password")
    if st.button("Proceed"):
        if auth_choice == "Create Account":
            with conn.session as session:
                session.execute(text("INSERT INTO users (username, password) VALUES (:u, :p)"), {"u": u_input, "p": make_hashes(p_input)})
                session.commit()
            st.success("Account created!")
        else:
            res = conn.query(f"SELECT password FROM users WHERE username = '{u_input}'", ttl=0)
            if not res.empty and check_hashes(p_input, res.iloc[0]['password']):
                st.session_state['logged_in'] = True
                st.rerun()
            else: st.error("Invalid Login")
else:
    st.sidebar.title(f"🛠️ {SHOP_NAME}")
    if st.sidebar.button("Logout"):
        st.session_state['logged_in'] = False
        st.rerun()

    tab_dash, tab_inv, tab_rev, tab_hist = st.tabs(["🚀 Dashboard", "📦 Inventory", "💰 Reports", "📜 History"])

    with tab_dash:
        st.header("New Rental")
        items_df = conn.query("SELECT * FROM inventory", ttl=0)
        items_df['available'] = items_df['total_qty'] - items_df['rented_qty']
        available_options = ["-- Select Item --"] + items_df[items_df['available'] > 0]['name'].tolist()

        with st.container(border=True):
            selected_item = st.selectbox("Select Item *", available_options)
            c1, c2 = st.columns(2)
            c_name = c1.text_input("Customer Name *")
            c_phone = c2.text_input("Customer Phone Number *")
            
            st.divider()
            st.subheader("Customer Photo (Optional)")
            photo_mode = st.radio("Select Photo Source", ["No Photo", "Take Live Photo", "Upload from Gallery"], horizontal=True)
            encoded_img = None
            if photo_mode == "Take Live Photo":
                img_file = st.camera_input("Capture Image")
                if img_file: encoded_img = base64.b64encode(img_file.getvalue()).decode()
            elif photo_mode == "Upload from Gallery":
                img_file = st.file_uploader("Choose an image", type=['png', 'jpg', 'jpeg'])
                if img_file: encoded_img = base64.b64encode(img_file.getvalue()).decode()

            st.divider()
            r1, r2 = st.columns(2)
            r_name, r_phone = r1.text_input("Referred By"), r2.text_input("Referral Phone")
            deposit, is_prepaid = st.number_input(f"Deposit ({CURRENCY})", min_value=0.0), st.checkbox("Fully Paid")

            if st.button("Rent Item"):
                if selected_item == "-- Select Item --" or not c_name or not c_phone:
                    st.error("Item, Name, and Phone are MANDATORY.")
                else:
                    item_id = int(items_df[items_df['name'] == selected_item]['id'].values[0])
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    with conn.session as session:
                        session.execute(text('''INSERT INTO rentals (item_id, customer_name, customer_phone, referred_by_name, referred_by_phone, start_time, status, deposit, is_paid, customer_photo) 
                                     VALUES (:i, :cn, :cp, :rn, :rp, :st, 'Active', :d, :ip, :ph)'''), 
                                     {"i": item_id, "cn": c_name, "cp": c_phone, "rn": r_name, "rp": r_phone, "st": now_str, "d": deposit, "ip": 1 if is_prepaid else 0, "ph": encoded_img})
                        session.execute(text("UPDATE inventory SET rented_qty = rented_qty + 1 WHERE id = :i"), {"i": item_id})
                        session.commit()
                    st.success("Rental Started!"); st.rerun()

        st.divider()
        st.header("⏳ Active Sessions")
        active = conn.query("SELECT r.*, i.name, i.rate FROM rentals r JOIN inventory i ON r.item_id = i.id WHERE r.status='Active'", ttl=0)
        for _, row in active.iterrows():
            with st.container(border=True):
                col_a, col_b = st.columns([1, 3])
                if row['customer_photo']: col_a.image(base64.b64decode(row['customer_photo']), width=100)
                col_b.write(f"**{row['name']}** -> {row['customer_name']} ({row['customer_phone']})")
                if col_b.button("Return Item", key=f"ret_{row['id']}", use_container_width=True):
                    start_dt = datetime.strptime(row['start_time'], "%Y-%m-%d %H:%M:%S")
                    days = max(1, (datetime.now() - start_dt).days + (1 if (datetime.now() - start_dt).seconds > 60 else 0))
                    total = days * row['rate']
                    with conn.session as session:
                        session.execute(text("UPDATE rentals SET status='Closed', total_bill=:t WHERE id=:id"), {"t": total, "id": int(row['id'])})
                        session.execute(text("UPDATE inventory SET rented_qty = rented_qty - 1 WHERE id=:i"), {"i": int(row['item_id'])})
                        session.commit()
                    st.rerun()

    with tab_inv:
        st.header("Inventory")
        with st.expander("➕ Add New Item"):
            cx, cy, cz = st.columns(3)
            n, r, q = cx.text_input("Item Name"), cy.number_input("Rate"), cz.number_input("Stock", min_value=1)
            if st.button("Save"):
                with conn.session as session:
                    session.execute(text("INSERT INTO inventory (name, rate, total_qty, rented_qty) VALUES (:n, :r, :q, 0)"), {"n": n, "r": r, "q": q})
                    session.commit(); st.rerun()
        inv_data = conn.query("SELECT name, rate, total_qty, rented_qty FROM inventory", ttl=0)
        st.dataframe(inv_data, use_container_width=True)

    with tab_rev:
        st.header("📊 Reports")
        history_df = conn.query("SELECT * FROM rentals WHERE status='Closed'", ttl=0)
        if not history_df.empty:
            history_df['date_obj'] = pd.to_datetime(history_df['start_time']).dt.date
            f_mode = st.radio("Duration", ["Today", "This Month", "Custom"], horizontal=True)
            if f_mode == "Today": start_f = end_f = date.today()
            elif f_mode == "This Month": start_f, end_f = date.today().replace(day=1), date.today()
            else: start_f, end_f = st.columns(2)[0].date_input("From"), st.columns(2)[1].date_input("To")
            f_df = history_df[(history_df['date_obj'] >= start_f) & (history_df['date_obj'] <= end_f)]
            st.metric("Total Revenue", f"{CURRENCY} {f_df['total_bill'].sum():,.2f}")
            if not f_df.empty:
                st.download_button("📥 Download PDF", generate_pdf(f_df, f_mode), f"Report_{f_mode}.pdf", "application/pdf")

    with tab_hist:
        st.header("📜 Full Records")
        search = st.text_input("🔍 Search Name or Phone Number").lower()
        full_df = conn.query("SELECT * FROM rentals WHERE status='Closed' ORDER BY id DESC", ttl=0)
        if search:
            full_df = full_df[full_df.apply(lambda r: search in str(r['customer_name']).lower() or search in str(r['customer_phone']), axis=1)]
        for _, row in full_df.iterrows():
            with st.expander(f"{row['customer_name']} | {row['start_time'][:10]}"):
                c1, c2 = st.columns([1, 3]); 
                if row['customer_photo']: c1.image(base64.b64decode(row['customer_photo']), width=150)
                c2.write(f"**Phone:** {row['customer_phone']} | **Bill:** {CURRENCY}{row['total_bill']}")
