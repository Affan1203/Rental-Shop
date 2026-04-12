import streamlit as st
import pandas as pd
from datetime import datetime
import sqlite3
import hashlib

# --- CONFIGURATION ---
SHOP_NAME = "Star Arts and Multiservices"
CURRENCY = "₹"

# --- DATABASE SETUP ---
conn = sqlite3.connect('star_arts_vault.db', check_same_thread=False)
c = conn.cursor()

# Create tables for Users, Inventory, and Rentals
c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, password TEXT)')
c.execute('''CREATE TABLE IF NOT EXISTS inventory 
             (id INTEGER PRIMARY KEY, name TEXT, rate REAL, total_qty INTEGER, rented_qty INTEGER)''')
c.execute('''CREATE TABLE IF NOT EXISTS rentals 
             (id INTEGER PRIMARY KEY, item_id INTEGER, customer_info TEXT, 
              start_time TEXT, status TEXT, total_bill REAL)''')
conn.commit()

# --- SECURITY FUNCTIONS ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return hashlib.sha256(str.encode(password)).hexdigest() == hashed_text

# --- APP LAYOUT ---
st.set_page_config(page_title=SHOP_NAME, page_icon="🏗️")

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# --- AUTHENTICATION INTERFACE ---
if not st.session_state['logged_in']:
    st.title(f"🔐 {SHOP_NAME}")
    auth_choice = st.radio("Access Portal", ["Login", "Create Account"])
    
    user = st.text_input("Username / Contact")
    pw = st.text_input("Password", type="password")

    if auth_choice == "Create Account":
        if st.button("Register New User"):
            if user and pw:
                c.execute('INSERT INTO users (username, password) VALUES (?,?)', (user, make_hashes(pw)))
                conn.commit()
                st.success("Account created successfully! Please switch to Login.")
            else:
                st.warning("Please fill in all fields.")
    else:
        if st.button("Login"):
            c.execute('SELECT password FROM users WHERE username = ?', (user,))
            result = c.fetchone()
            if result and check_hashes(pw, result[0]):
                st.session_state['logged_in'] = True
                st.rerun()
            else:
                st.error("Invalid Username or Password")

else:
    # --- MAIN DASHBOARD ---
    st.sidebar.title(f"🛠️ {SHOP_NAME}")
    if st.sidebar.button("Logout"):
        st.session_state['logged_in'] = False
        st.rerun()

    st.title("Shop Management Dashboard")
    
    tab1, tab2, tab3 = st.tabs(["📦 Inventory", "⏳ Active Rentals", "📜 History"])

    with tab1:
        st.header("Manage Stock")
        with st.expander("➕ Add New Construction Item"):
            col1, col2, col3 = st.columns([3, 1, 1])
            name = col1.text_input("Item Name (e.g., Ladder, Mixer)")
            rate = col2.number_input(f"Rate ({CURRENCY}/Day)", min_value=0)
            qty = col3.number_input("Stock Quantity", min_value=1)
            
            if st.button("Add to Inventory"):
                c.execute('INSERT INTO inventory (name, rate, total_qty, rented_qty) VALUES (?,?,?,0)', (name, rate, qty))
                conn.commit()
                st.rerun()

        # Display items
        items = pd.read_sql("SELECT * FROM inventory", conn)
        for _, row in items.iterrows():
            available = row['total_qty'] - row['rented_qty']
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 2, 2])
                c1.write(f"### {row['name']}")
                c1.write(f"Rate: {CURRENCY}{row['rate']}/day")
                c2.metric("Available Stock", f"{available} / {row['total_qty']}")
                
                if available > 0:
                    with c3.expander("Assign to Customer"):
                        cust = st.text_input("Customer Name/Phone", key=f"cust_{row['id']}")
                        if st.button("Confirm Rental", key=f"btn_{row['id']}"):
                            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            c.execute('INSERT INTO rentals (item_id, customer_info, start_time, status) VALUES (?,?,?, "Active")', (row['id'], cust, now))
                            c.execute('UPDATE inventory SET rented_qty = rented_qty + 1 WHERE id = ?', (row['id'],))
                            conn.commit()
                            st.rerun()
                else:
                    c3.error("All units are currently out.")

    with tab2:
        st.header("Currently Rented")
        active = pd.read_sql("""SELECT r.id, i.name, r.customer_info, r.start_time, i.rate, i.id as item_id 
                                FROM rentals r JOIN inventory i ON r.item_id = i.id WHERE r.status='Active'""", conn)
        
        if active.empty:
            st.info("No items are currently out on rent.")
        
        for _, row in active.iterrows():
            with st.container(border=True):
                st.write(f"**Item:** {row['name']} | **Customer:** {row['customer_info']}")
                st.write(f"**Rent Started:** {row['start_time']}")
                
                if st.button(f"Return & Close Session (Ref: {row['id']})"):
                    # Logic: Min 1 day, then round up for any extra time
                    start = datetime.strptime(row['start_time'], "%Y-%m-%d %H:%M:%S")
                    diff = datetime.now() - start
                    days = diff.days + (1 if diff.seconds > 0 else 0)
                    if days == 0: days = 1
                    
                    bill = days * row['rate']
                    
                    c.execute('UPDATE rentals SET status="Closed", total_bill=? WHERE id=?', (bill, row['id']))
                    c.execute('UPDATE inventory SET rented_qty = rented_qty - 1 WHERE id=?', (row['item_id'],))
                    conn.commit()
                    st.success(f"Item Returned! Total Bill for {days} day(s): {CURRENCY}{bill}")
                    st.rerun()

    with tab3:
        st.header("Transaction History")
        history = pd.read_sql("SELECT customer_info as Customer, start_time as Started, total_bill as Bill FROM rentals WHERE status='Closed'", conn)
        st.dataframe(history, use_container_width=True)
