import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import sqlite3
import hashlib
import base64
from fpdf import FPDF
from io import BytesIO

# --- CONFIGURATION ---
SHOP_NAME = "Star Arts and Multiservices"
CURRENCY = "Rs."

# --- DATABASE SETUP ---
conn = sqlite3.connect('star_arts_vault.db', check_same_thread=False)
c = conn.cursor()

c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, password TEXT)')
c.execute('''CREATE TABLE IF NOT EXISTS inventory 
             (id INTEGER PRIMARY KEY, name TEXT, rate REAL, total_qty INTEGER, rented_qty INTEGER)''')
c.execute('''CREATE TABLE IF NOT EXISTS rentals 
             (id INTEGER PRIMARY KEY, item_id INTEGER, customer_name TEXT, customer_phone TEXT,
              referred_by_name TEXT, referred_by_phone TEXT,
              start_time TEXT, status TEXT, deposit REAL, total_bill REAL, is_paid INTEGER, customer_photo TEXT)''')
conn.commit()

# --- HELPER FUNCTIONS ---
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
        pdf.cell(45, 10, str(row['customer_name'])[:18], 1); pdf.cell(35, 10, str(row['start_time'])[:11], 1); pdf.cell(45, 10, str(row['referred_by_name'])[:18], 1); pdf.cell(35, 10, f"{row['total_bill']}", 1); pdf.cell(30, 10, "Paid" if row['is_paid'] else "Settled", 1); pdf.ln()
        total_sum += row['total_bill']
    pdf.ln(5); pdf.set_font("Arial", 'B', 12); pdf.cell(200, 10, txt=f"Grand Total: {CURRENCY} {total_sum:,.2f}", ln=True, align='R')
    return pdf.output(dest='S').encode('latin-1')

def make_hashes(password): return hashlib.sha256(str.encode(password)).hexdigest()
def check_hashes(password, hashed_text): return hashlib.sha256(str.encode(password)).hexdigest() == hashed_text

# --- AUTHENTICATION ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.title(f"🔐 {SHOP_NAME}")
    auth_choice = st.radio("Portal", ["Login", "Create Account"])
    user = st.text_input("Username")
    pw = st.text_input("Password", type="password")
    if st.button("Proceed"):
        if auth_choice == "Create Account":
            c.execute('INSERT INTO users (username, password) VALUES (?,?)', (user, make_hashes(pw)))
            conn.commit(); st.success("Account created!")
        else:
            c.execute('SELECT password FROM users WHERE username = ?', (user,))
            res = c.fetchone()
            if res and check_hashes(pw, res[0]):
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
        items_df = pd.read_sql("SELECT * FROM inventory", conn)
        items_df['available'] = items_df['total_qty'] - items_df['rented_qty']
        available_options = ["-- Select Item to Rent --"] + items_df[items_df['available'] > 0]['name'].tolist()

        with st.container(border=True):
            selected_item = st.selectbox("Select Item to Rent", available_options)
            c1, c2 = st.columns(2)
            c_name, c_phone = c1.text_input("Customer Name"), c2.text_input("Customer Phone")
            r1, r2 = st.columns(2)
            r_name, r_phone = r1.text_input("Referral Name"), r2.text_input("Referral Phone")
            
            st.write("---")
            st.subheader("Customer Photo")
            img_file = st.camera_input("Take a photo of the customer")
            encoded_img = None
            if img_file:
                encoded_img = base64.b64encode(img_file.getvalue()).decode()
            
            deposit, is_prepaid = st.number_input(f"Deposit ({CURRENCY})", min_value=0.0), st.checkbox("Fully Paid")

            if st.button("Rent Item"):
                if selected_item != "-- Select Item to Rent --" and c_name:
                    item_id = items_df[items_df['name'] == selected_item]['id'].values[0]
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute('''INSERT INTO rentals (item_id, customer_name, customer_phone, referred_by_name, referred_by_phone, start_time, status, deposit, is_paid, customer_photo) 
                                 VALUES (?,?,?,?,?,?,'Active',?,?,?)''', 
                              (int(item_id), c_name, c_phone, r_name, r_phone, now_str, deposit, 1 if is_prepaid else 0, encoded_img))
                    c.execute('UPDATE inventory SET rented_qty = rented_qty + 1 WHERE id = ?', (int(item_id),))
                    conn.commit(); st.rerun()

        st.divider()
        st.header("⏳ Active Sessions")
        active = pd.read_sql("SELECT r.*, i.name, i.rate FROM rentals r JOIN inventory i ON r.item_id = i.id WHERE r.status='Active'", conn)
        for _, row in active.iterrows():
            with st.container(border=True):
                col_a, col_b = st.columns([1, 3])
                if row['customer_photo']:
                    col_a.image(base64.b64decode(row['customer_photo']), width=100)
                else:
                    col_a.write("No Photo")
                
                col_b.write(f"**{row['name']}** -> {row['customer_name']}")
                if col_b.button("Return Item", key=f"ret_{row['id']}", use_container_width=True):
                    start_dt = datetime.strptime(row['start_time'], "%Y-%m-%d %H:%M:%S")
                    days = max(1, (datetime.now() - start_dt).days + (1 if (datetime.now() - start_dt).seconds > 60 else 0))
                    total = days * row['rate']
                    c.execute('UPDATE rentals SET status="Closed", total_bill=? WHERE id=?', (total, row['id']))
                    c.execute('UPDATE inventory SET rented_qty = rented_qty - 1 WHERE id=?', (row['item_id'],))
                    conn.commit(); st.rerun()

    with tab_inv:
        st.header("Inventory Management")
        with st.expander("➕ Add New Item"):
            cx, cy, cz = st.columns(3)
            n, r, q = cx.text_input("Item Name"), cy.number_input("Rate"), cz.number_input("Stock", min_value=1)
            if st.button("Save"):
                c.execute('INSERT INTO inventory (name, rate, total_qty, rented_qty) VALUES (?,?,?,0)', (n, r, q))
                conn.commit(); st.rerun()
        st.dataframe(pd.read_sql("SELECT name, rate, total_qty as Stock, rented_qty as Rented FROM inventory", conn), use_container_width=True)

    with tab_rev:
        st.header("📊 Reports")
        history_df = pd.read_sql("SELECT * FROM rentals WHERE status='Closed'", conn)
        if not history_df.empty:
            history_df['date_obj'] = pd.to_datetime(history_df['start_time']).dt.date
            filter_mode = st.radio("Duration", ["Today", "This Month", "Custom Range"], horizontal=True)
            if filter_mode == "Today": start_f = end_f = date.today()
            elif filter_mode == "This Month": start_f, end_f = date.today().replace(day=1), date.today()
            else: start_f, end_f = st.columns(2)[0].date_input("From"), st.columns(2)[1].date_input("To")
            f_df = history_df[(history_df['date_obj'] >= start_f) & (history_df['date_obj'] <= end_f)]
            st.metric(f"Revenue", f"{CURRENCY} {f_df['total_bill'].sum():,.2f}")
            if not f_df.empty:
                st.download_button("📥 Download PDF", generate_pdf(f_df, filter_mode), f"Report_{filter_mode}.pdf", "application/pdf")

    with tab_hist:
        st.header("📜 History & Search")
        all_hist = pd.read_sql("SELECT * FROM rentals WHERE status='Closed' ORDER BY id DESC", conn)
        search_query = st.text_input("🔍 Search by Name or Phone").lower()
        if search_query:
            all_hist = all_hist[all_hist.apply(lambda row: search_query in str(row['customer_name']).lower() or search_query in str(row['customer_phone']), axis=1)]
        
        for _, row in all_hist.iterrows():
            with st.expander(f"{row['customer_name']} - {row['start_time'][:10]}"):
                c_img, c_txt = st.columns([1, 3])
                if row['customer_photo']: c_img.image(base64.b64decode(row['customer_photo']), width=150)
                c_txt.write(f"**Phone:** {row['customer_phone']}")
                c_txt.write(f"**Total Bill:** {CURRENCY} {row['total_bill']}")
                if row['referred_by_name']: c_txt.write(f"**Referral:** {row['referred_by_name']}")
