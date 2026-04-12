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
             (id INTEGER PRIMARY KEY, item_id INTEGER, customer_name TEXT, customer_phone TEXT,
              start_time TEXT, status TEXT, deposit REAL, total_bill REAL, is_paid INTEGER)''')
conn.commit()

def make_hashes(password): return hashlib.sha256(str.encode(password)).hexdigest()
def check_hashes(password, hashed_text): return hashlib.sha256(str.encode(password)).hexdigest() == hashed_text

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

    tab_dash, tab_inv, tab_rev, tab_hist = st.tabs(["🚀 Dashboard", "📦 Inventory", "💰 Revenue", "📜 History"])

    with tab_dash:
        st.header("New Rental")
        items_df = pd.read_sql("SELECT * FROM inventory", conn)
        items_df['available'] = items_df['total_qty'] - items_df['rented_qty']
        
        available_options = ["-- Select Item to Rent --"] + items_df[items_df['available'] > 0]['name'].tolist()

        with st.container(border=True):
            selected_item = st.selectbox("Item Selection", available_options)
            c_name = st.text_input("Customer Name")
            c_phone = st.text_input("Customer Phone")
            deposit = st.number_input(f"Advance Deposit ({CURRENCY})", min_value=0.0, step=10.0)
            is_prepaid = st.checkbox("Mark as Full Payment Received (Paid)")

            if st.button("Rent Item"):
                if selected_item != "-- Select Item to Rent --" and c_name:
                    item_id = items_df[items_df['name'] == selected_item]['id'].values[0]
                    # We store the raw ISO format for easier math later
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute('''INSERT INTO rentals (item_id, customer_name, customer_phone, start_time, status, deposit, is_paid) 
                                 VALUES (?,?,?,?,'Active',?,?)''', 
                              (int(item_id), c_name, c_phone, now_str, deposit, 1 if is_prepaid else 0))
                    c.execute('UPDATE inventory SET rented_qty = rented_qty + 1 WHERE id = ?', (int(item_id),))
                    conn.commit()
                    st.success(f"Successfully Rented {selected_item}")
                    st.rerun()
                else:
                    st.error("Please select an item and enter customer name.")

        st.divider()
        st.header("⏳ Active Rentals")
        active = pd.read_sql("""SELECT r.*, i.name, i.rate FROM rentals r 
                                JOIN inventory i ON r.item_id = i.id WHERE r.status='Active'""", conn)
        
        for _, row in active.iterrows():
            with st.container(border=True):
                col_a, col_b = st.columns([3, 1.2])
                # Format the time for display
                display_time = datetime.strptime(row['start_time'], "%Y-%m-%d %H:%M:%S").strftime("%I:%M %p | %d %b")
                status_label = "✅ PAID" if row['is_paid'] else f"💰 Deposit: {CURRENCY}{row['deposit']}"
                
                col_a.write(f"**{row['name']}** -> {row['customer_name']}")
                col_a.caption(f"🕒 Since: {display_time} | {status_label}")
                
                if col_b.button("Return & Bill", key=f"ret_{row['id']}", use_container_width=True):
                    start_dt = datetime.strptime(row['start_time'], "%Y-%m-%d %H:%M:%S")
                    diff = datetime.now() - start_dt
                    days = diff.days + (1 if diff.seconds > 60 else 0)
                    if days == 0: days = 1
                    
                    total = days * row['rate']
                    balance = max(0.0, total - row['deposit'])
                    
                    st.session_state[f"bill_{row['id']}"] = {"total": total, "balance": balance, "days": days, "item_id": row['item_id']}

                if f"bill_{row['id']}" in st.session_state:
                    b = st.session_state[f"bill_{row['id']}"]
                    st.info(f"Final Bill: {CURRENCY}{b['total']} ({b['days']} days)")
                    if not row['is_paid']:
                        st.warning(f"Collect Balance: {CURRENCY}{b['balance']}")
                    
                    if st.button("Confirm & Close", key=f"conf_{row['id']}"):
                        close_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        c.execute('UPDATE rentals SET status="Closed", total_bill=? WHERE id=?', (b['total'], row['id']))
                        c.execute('UPDATE inventory SET rented_qty = rented_qty - 1 WHERE id=?', (b['item_id'],))
                        conn.commit()
                        del st.session_state[f"bill_{row['id']}"]
                        st.rerun()

    with tab_inv:
        st.header("Inventory Settings")
        with st.expander("➕ Add New Item"):
            c1, c2, c3 = st.columns(3)
            n, r, q = c1.text_input("Name"), c2.number_input("Rate/Day"), c3.number_input("Stock", min_value=1)
            if st.button("Save Item"):
                c.execute('INSERT INTO inventory (name, rate, total_qty, rented_qty) VALUES (?,?,?,0)', (n, r, q))
                conn.commit(); st.rerun()
        
        st.write("Current Items:")
        inv_data = pd.read_sql("SELECT * FROM inventory", conn)
        st.dataframe(inv_data[['name', 'rate', 'total_qty', 'rented_qty']], use_container_width=True)

    with tab_rev:
        st.header("Financial Revenue")
        history_df = pd.read_sql("SELECT * FROM rentals WHERE status='Closed'", conn)
        
        if not history_df.empty:
            # Convert string dates to actual Python dates for filtering
            history_df['date_obj'] = pd.to_datetime(history_df['start_time'])
            today = datetime.now().date()
            this_month = datetime.now().month
            
            daily_rev = history_df[history_df['date_obj'].dt.date == today]['total_bill'].sum()
            monthly_rev = history_df[history_df['date_obj'].dt.month == this_month]['total_bill'].sum()
            
            col1, col2 = st.columns(2)
            col1.metric("Today's Revenue", f"{CURRENCY}{daily_rev:,.2f}")
            col2.metric("This Month's Revenue", f"{CURRENCY}{monthly_rev:,.2f}")
            
            st.divider()
            st.subheader("Revenue Details")
            st.dataframe(history_df[['customer_name', 'total_bill', 'start_time']], use_container_width=True)
        else:
            st.info("No closed transactions yet to calculate revenue.")

    with tab_hist:
        st.header("Full History")
        st.dataframe(pd.read_sql("SELECT customer_name, customer_phone, start_time, total_bill FROM rentals WHERE status='Closed'", conn), use_container_width=True)
