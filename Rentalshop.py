import streamlit as st
import pandas as pd
from datetime import datetime
import sqlite3
import hashlib

# --- DATABASE SETUP ---
conn = sqlite3.connect('shop_vault.db', check_same_thread=False)
c = conn.cursor()

# Tables for Users, Inventory, and Rentals
c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, contact TEXT, password TEXT)')
c.execute('''CREATE TABLE IF NOT EXISTS inventory 
             (id INTEGER PRIMARY KEY, name TEXT, rate REAL, total_qty INTEGER, rented_qty INTEGER)''')
c.execute('''CREATE TABLE IF NOT EXISTS rentals 
             (id INTEGER PRIMARY KEY, item_id INTEGER, customer_contact TEXT, 
              start_time TEXT, status TEXT, total_bill REAL)''')
conn.commit()

# --- HELPER FUNCTIONS ---
def make_hashes(password): return hashlib.sha256(str.encode(password)).hexdigest()
def check_hashes(password, hashed_text): return make_hashes(password) == hashed_text

# --- AUTHENTICATION UI ---
if 'auth_state' not in st.session_state: st.session_state['auth_state'] = False

if not st.session_state['auth_state']:
    st.title("🏗️ Rental Shop Manager")
    auth_mode = st.radio("Choose Action", ["Login", "Sign Up"])
    
    contact = st.text_input("Email or Phone Number")
    password = st.text_input("Password", type="password")

    if auth_mode == "Sign Up":
        confirm_pw = st.text_input("Confirm Password", type="password")
        if st.button("Create Account"):
            if password == confirm_pw and contact:
                c.execute('INSERT INTO users (contact, password) VALUES (?,?)', (contact, make_hashes(password)))
                conn.commit()
                st.success("Account created! Please switch to Login.")
            else: st.error("Passwords do not match or field empty.")
    
    else:
        if st.button("Login"):
            c.execute('SELECT password FROM users WHERE contact = ?', (contact,))
            user_pw = c.fetchone()
            if user_pw and check_hashes(password, user_pw[0]):
                st.session_state['auth_state'] = True
                st.rerun()
            else: st.error("Invalid Credentials")

else:
    # --- MAIN DASHBOARD ---
    st.sidebar.button("Logout", on_click=lambda: st.session_state.update({'auth_state': False}))
    st.title("📋 Shop Dashboard")
    
    tab1, tab2 = st.tabs(["Inventory & Renting", "Active Sessions"])

    with tab1:
        # 1. ADD NEW ITEM (With Quantity)
        with st.expander("➕ Add New Equipment"):
            col1, col2, col3 = st.columns(3)
            name = col1.text_input("Item Name")
            rate = col2.number_input("Rate (₹/Day)", min_value=0)
            qty = col3.number_input("Total Quantity", min_value=1)
            if st.button("Add Item"):
                c.execute('INSERT INTO inventory (name, rate, total_qty, rented_qty) VALUES (?,?,?,0)', (name, rate, qty))
                conn.commit()
                st.rerun()

        # 2. INVENTORY LIST (Check Stock)
        st.subheader("Current Stock")
        items = pd.read_sql("SELECT * FROM inventory", conn)
        for _, row in items.iterrows():
            available = row['total_qty'] - row['rented_qty']
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 2])
                c1.write(f"**{row['name']}**")
                c2.write(f"In Stock: **{available}** / {row['total_qty']}")
                
                if available > 0:
                    with c3.expander("Rent Out"):
                        cust = st.text_input("Customer Phone", key=f"c_{row['id']}")
                        if st.button("Confirm Rent", key=f"b_{row['id']}"):
                            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            c.execute('INSERT INTO rentals (item_id, customer_contact, start_time, status) VALUES (?,?,?, "Active")', (row['id'], cust, now))
                            c.execute('UPDATE inventory SET rented_qty = rented_qty + 1 WHERE id = ?', (row['id'],))
                            conn.commit()
                            st.rerun()
                else:
                    c3.error("Out of Stock")

    with tab2:
        st.subheader("Active Rentals")
        active = pd.read_sql("""SELECT r.id, i.name, r.customer_contact, r.start_time, i.rate, i.id as item_id 
                                FROM rentals r JOIN inventory i ON r.item_id = i.id WHERE r.status='Active'""", conn)
        
        for _, row in active.iterrows():
            with st.container(border=True):
                st.write(f"📦 {row['name']} -> 👤 {row['customer_contact']}")
                if st.button(f"Return Item (ID: {row['id']})"):
                    # Calculate bill (Round up logic)
                    start = datetime.strptime(row['start_time'], "%Y-%m-%d %H:%M:%S")
                    diff = datetime.now() - start
                    days = max(1, diff.days + (1 if diff.seconds > 0 else 0))
                    bill = days * row['rate']
                    
                    c.execute('UPDATE rentals SET status="Closed", total_bill=? WHERE id=?', (bill, row['id']))
                    c.execute('UPDATE inventory SET rented_qty = rented_qty - 1 WHERE id=?', (row['item_id'],))
                    conn.commit()
                    st.success(f"Return Successful! Total: ₹{bill}")
                    st.rerun()
