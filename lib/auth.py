import streamlit as st
from lib.supabase_client import get_supabase_client
from lib.utils import format_currency

def init_auth_session():
    """Initializes session state variables for authentication."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user" not in st.session_state:
        st.session_state.user = None

def login(email, password) -> bool:
    """
    Authenticates a user against Supabase Auth.
    If successful, checks their role and active status in public.profiles.
    """
    supabase = get_supabase_client()
    try:
        # Authenticate using Supabase Auth
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        if res.user:
            # Query custom profile to check role and status
            profile_res = supabase.table("profiles").select("*").eq("id", res.user.id).execute()
            if len(profile_res.data) > 0:
                profile = profile_res.data[0]
                if not profile.get("active", True):
                    st.error("Esta cuenta ha sido desactivada por el administrador.")
                    supabase.auth.sign_out()
                    return False
                
                # Save session
                st.session_state.authenticated = True
                st.session_state.user = {
                    "id": profile["id"],
                    "email": profile["email"],
                    "full_name": profile["full_name"],
                    "role": profile["role"]
                }
                return True
            else:
                st.error("No se encontró un perfil asociado a esta cuenta.")
                supabase.auth.sign_out()
                return False
    except Exception as e:
        error_msg = str(e)
        if "Invalid login credentials" in error_msg:
            st.error("Credenciales incorrectas. Intente nuevamente.")
        else:
            st.error(f"Error de inicio de sesión: {error_msg}")
        return False
    return False

def logout():
    """Logs out the user and clears session state."""
    supabase = get_supabase_client()
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state.authenticated = False
    st.session_state.user = None
    st.rerun()

def get_current_user():
    """Returns the current logged-in user profile dictionary or None."""
    init_auth_session()
    return st.session_state.user

def check_permission(required_roles: list) -> bool:
    """
    Checks if the currently logged-in user has one of the required roles.
    If not, returns False.
    """
    user = get_current_user()
    if not user:
        return False
    return user["role"] in required_roles

def require_auth():
    """
    Checks if a user is authenticated.
    If not, stops Streamlit execution and shows a warning.
    """
    init_auth_session()
    if not st.session_state.authenticated:
        st.warning("Debe iniciar sesión para acceder a esta página.")
        st.stop()

def auth_gate():
    """
    Secure gateway to call at the top of Streamlit pages.
    Displays a modern login interface if unauthenticated and stops execution.
    """
    init_auth_session()
    if not st.session_state.authenticated:
        # Centered modern login box
        st.markdown("<h2 style='text-align: center; color: #1E3D59;'>GNB Soluciones Industriales</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #666;'>Sistema Back Office / Control de Planillas</p>", unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            with st.form("login_form", clear_on_submit=False):
                st.subheader("Iniciar Sesión")
                email = st.text_input("Correo electrónico", placeholder="admin@gnb.com")
                password = st.text_input("Contraseña", type="password", placeholder="******")
                submit = st.form_submit_button("Entrar", use_container_width=True)
                
                if submit:
                    if not email or not password:
                        st.error("Por favor complete todos los campos.")
                    else:
                        with st.spinner("Autenticando..."):
                            if login(email, password):
                                st.success("¡Acceso concedido!")
                                st.rerun()
                                
        st.stop()
        
    # Render user profile info in the sidebar automatically when authenticated
    with st.sidebar:
        user = st.session_state.user
        st.markdown(f"**Usuario:** {user['full_name']}")
        st.markdown(f"**Rol:** `{user['role'].upper()}`")
        if st.button("Cerrar Sesión", use_container_width=True, key="sidebar_logout_btn"):
            logout()
        st.markdown("---")
