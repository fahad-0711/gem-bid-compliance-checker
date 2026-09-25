"""
Login/Register gate for the Streamlit app.
Call `require_login()` at the very top of app/app.py, before any other UI code.
It returns immediately (doing nothing) once the user is logged in;
otherwise it renders the login/register form and stops the script.
"""

import streamlit as st
from auth import register_user, verify_user


def require_login():
    if st.session_state.get("logged_in"):
        return  # already logged in — let app.py continue to the main page

    st.title("🔐 GeM Bid Compliance Checker — Login")

    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Log in")

        if submitted:
            if verify_user(username, password):
                st.session_state["logged_in"] = True
                st.session_state["username"] = username.strip()
                st.rerun()
            else:
                st.error("Incorrect username or password.")

    with tab_register:
        with st.form("register_form"):
            new_username = st.text_input("Choose a username", key="reg_username")
            new_password = st.text_input("Choose a password", type="password", key="reg_password")
            confirm_password = st.text_input("Confirm password", type="password", key="reg_confirm")
            reg_submitted = st.form_submit_button("Register")

        if reg_submitted:
            if new_password != confirm_password:
                st.error("Passwords do not match.")
            else:
                success, message = register_user(new_username, new_password)
                if success:
                    st.success(message + " Switch to the Login tab.")
                else:
                    st.error(message)

    st.stop()  # halt execution so the main page never renders while logged out
