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
    url = None
    key = None
    try:
        url = st.secrets.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY")
    except Exception:
        # st.secrets raises an exception if no secrets.toml exists at all
        pass
    
    # 2. Fallback to Environment Variables
    if not url:
        url = os.getenv("SUPABASE_URL") or os.getenv("EXPO_PUBLIC_SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    if not key:
        key = os.getenv("SUPABASE_KEY") or os.getenv("EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
        
    if not url or not key:
        raise ValueError(
            "Supabase credentials not found. Please configure Supabase variables (SUPABASE_URL, EXPO_PUBLIC_SUPABASE_URL, or NEXT_PUBLIC_SUPABASE_URL) "
            "and keys in your .env file or Streamlit Secrets."
        )
        
    return create_client(url, key)
