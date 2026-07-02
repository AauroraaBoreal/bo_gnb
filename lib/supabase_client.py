import os
import streamlit as st
from supabase import create_client, Client
from dotenv import load_dotenv

# Load .env file for local development
load_dotenv()

@st.cache_resource
def get_supabase_client() -> Client:
    """
    Initializes and returns a cached Supabase client.
    Reads credentials from Streamlit secrets (for Cloud deployment) or from environment variables (local development).
    """
    # 1. Try to read from Streamlit Secrets
    url = st.secrets.get("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_KEY")
    service_role_key = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY")
    
    # 2. Fallback to Environment Variables
    if not url:
        url = os.getenv("SUPABASE_URL")
    if not key:
        key = os.getenv("SUPABASE_KEY")
    if not service_role_key:
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
    if not url or not key:
        raise ValueError(
            "Supabase credentials not found. Please configure SUPABASE_URL and SUPABASE_KEY "
            "in your .env file or Streamlit Secrets."
        )
        
    return create_client(url, key)

@st.cache_resource
def get_supabase_admin_client() -> Client:
    """
    Initializes and returns a cached Supabase client using the Service Role Key.
    Use this ONLY when bypassing RLS is required (e.g. creating user accounts programmatically).
    """
    url = st.secrets.get("SUPABASE_URL")
    service_role_key = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY")
    
    if not url:
        url = os.getenv("SUPABASE_URL")
    if not service_role_key:
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
    if not url or not service_role_key:
        raise ValueError(
            "Supabase Service Role Key not found. Please configure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
        )
        
    return create_client(url, service_role_key)
