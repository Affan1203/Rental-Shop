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

c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, password TEXT)')
c.execute('''CREATE TABLE IF NOT EXISTS inventory 
             (id INTEGER PRIMARY KEY, name TEXT, rate REAL, total_qty INTEGER, rented_qty INTEGER)''')
c.execute('''CREATE TABLE IF NOT EXISTS rentals 
             (id INTEGER PRIMARY KEY, item_id INTEGER, customer_info TEXT, 
              start_time TEXT, status TEXT, total_bill REAL)''')
conn.commit()

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
            conn.commit()
            st.success("Account created! Now Login.")
        else:
            c.execute('SELECT password FROM users WHERE username = ?', (user,))
            res = c.fetchone()
            if res and check_hashes(pw, res[0]):
                st.session_state['logged_in'] = True
                st.rerun()
            else: st.error("Wrong credentials")
else:
    st.sidebar.title(f"🛠️ {SHOP_NAME}")
    if st.sidebar.button("Logout"):
        st.session_state['logged_in'] = False
        st.rerun()

    # --- MAIN TABS ---
    tab_dash, tab_inv, tab_hist = st.tabs(["🚀 Dashboard", "📦 Shop Inventory", "📜 History"])

    with tab_dash:
        st.header("Start New Rental")
        items_df = pd.read_sql("SELECT * FROM inventory", conn)
        items_df['available'] = items_df['total_qty'] - items_df['rented_qty']
        available_items = items_df[items_df['available'] > 0]

        with st.container(border=True):
            if not available_items.empty:
                selected_item_name = st.selectbox("Select Item to Rent", available_items['name'].tolist())
                cust_info = st.text_input("Customer Name/Phone")
                if st.button("Confirm Rental & Start Timer"):
                    item_id = items_df[items_df['name'] == selected_item_name]['id'].values[0]
                    now = datetime.now().strftime("%I:%M %p | %d %b %Y")
                    c.execute('INSERT INTO rentals (item_id, customer_info, start_time, status) VALUES (?,?,?, "Active")', (int(item_id), cust_info, now))
                    c.execute('UPDATE inventory SET rented_qty = rented_qty + 1 WHERE id = ?', (int(item_id),))
                    conn.commit()
                    st.success(f"Rented {selected_item_name} to {cust_info}")
                    st.rerun()
            else:
                st.warning("No items available in stock to rent out.")

        st.divider()
        st.header("⏳ Active Sessions")
        active = pd.read_sql("""SELECT r.id, i.name, r.customer_info, r.start_time, i.rate, i.id as item_id 
                                FROM rentals r JOIN inventory i ON r.item_id = i.id WHERE r.status='Active'""", conn)
        
        for _, row in active.iterrows():
            with st.container(border=True):
                col_a, col_b = st.columns([3, 1.2])
                col_a.write(f"**Item:** {row['name']} | **Customer:** {row['customer_info']}")
                col_a.caption(f"🕒 Rented at: {row['start_time']}")
                
                if col_b.button("Close & Bill", key=f"close_{row['id']}", use_container_width=True):
                    start_dt = datetime.strptime(row['start_time'], "%I:%M %p | %d %b %Y")
                    diff = datetime.now() - start_dt
                    days = diff.days + (1 if diff.seconds > 60 else 0)
                    if days == 0: days = 1
                    bill = days * row['rate']
                    
                    c.execute('UPDATE rentals SET status="Closed", total_bill=? WHERE id=?', (bill, row['id']))
                    c.execute('UPDATE inventory SET rented_qty = rented_qty - 1 WHERE id=?', (row['item_id'],))
                    conn.commit()
                    st.success(f"Total Bill: {CURRENCY}{bill}")
                    st.rerun()

    with tab_inv:
        st.header("Shop Inventory Management")
        
        with st.expander("➕ Add New Item to Shop"):
            c1, c2, c3 = st.columns(3)
            new_n = c1.text_input("Item Name")
            new_r = c2.number_input("Rate/Day", min_value=0.0)
            new_q = c3.number_input("Total Stock", min_value=1)
            if st.button("Save New Item"):
                c.execute('INSERT INTO inventory (name, rate, total_qty, rented_qty) VALUES (?,?,?,0)', (new_n, new_r, new_q))
                conn.commit()
                st.rerun()

        st.divider()
        for _, row in items_df.iterrows():
            with st.expander(f"⚙️ Manage: {row['name']} (Stock: {row['total_qty']})"):
                e1, e2, e3 = st.columns(3)
                edit_n = e1.text_input("Name", value=row['name'], key=f"en_{row['id']}")
                edit_r = e2.number_input("Rate", value=float(row['rate']), key=f"er_{row['id']}")
                edit_q = e3.number_input("Total Stock", value=int(row['total_qty']), key=f"eq_{row['id']}")
                
                col_up, col_del = st.columns(2)
                if col_up.button("Update Item", key=f"up_{row['id']}", use_container_width=True):
                    c.execute('UPDATE inventory SET name=?, rate=?, total_qty=? WHERE id=?', (edit_n, edit_r, edit_q, row['id']))
                    conn.commit()
                    st.success("Updated!")
                    st.rerun()
                
                # Delete logic with confirmation
                st.write("---")
                if col_del.button("🗑️ Delete Item", key=f"del_init_{row['id']}", use_container_width=True, type="secondary"):
                    st.session_state[f"confirm_delete_{row['id']}"] = True
                
                if st.session_state.get(f"confirm_delete_{row['id']}", False):
                    st.warning(f"Are you sure you want to delete '{row['name']}'? This cannot be undone.")
                    confirm_check = st.checkbox("Yes, I am sure.", key=f"check_{row['id']}")
                    if confirm_check:
                        if st.button("🔥 Permanently Delete", key=f"del_final_{row['id']}", type="primary"):
                            c.execute('DELETE FROM inventory WHERE id=?', (row['id'],))
                            conn.commit()
                            st.rerun()
                    if st.button("Cancel", key=f"can_{row['id']}"):
                        st.session_state[f"confirm_delete_{row['id']}"] = False
                        st.rerun()

    with tab_hist:
        st.header("Closed Transactions")
        history = pd.read_sql("SELECT customer_info as Customer, start_time as Rented_At, total_bill as Bill_Paid FROM rentals WHERE status='Closed' ORDER BY id DESC", conn)
        st.dataframe(history, use_container_width=True)
