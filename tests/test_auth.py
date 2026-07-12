import pytest
from unittest.mock import MagicMock, patch
import streamlit as st
from lib.auth import (
    init_auth_session, login, register, logout,
    get_current_user, check_permission, require_auth
)

def test_init_auth_session(mock_streamlit_session_state):
    init_auth_session()
    assert mock_streamlit_session_state.authenticated is False
    assert mock_streamlit_session_state.user is None

def test_login_success(supabase_mock, mock_streamlit_session_state):
    # Mock auth response
    mock_user = MagicMock()
    mock_user.id = "user_123"
    res = MagicMock()
    res.user = mock_user
    supabase_mock.auth.sign_in_with_password.return_value = res
    
    # Mock profiles table
    supabase_mock.set_table_data("profiles", [{
        "id": "user_123",
        "email": "test@example.com",
        "full_name": "Test User",
        "role": "admin",
        "active": True
    }])
    
    success = login("test@example.com", "password")
    assert success is True
    assert mock_streamlit_session_state.authenticated is True
    assert mock_streamlit_session_state.user["id"] == "user_123"
    assert mock_streamlit_session_state.user["role"] == "admin"

def test_login_inactive_account(supabase_mock, mock_streamlit_session_state):
    mock_user = MagicMock()
    mock_user.id = "user_123"
    res = MagicMock()
    res.user = mock_user
    supabase_mock.auth.sign_in_with_password.return_value = res
    
    # Mock profile is inactive
    supabase_mock.set_table_data("profiles", [{
        "id": "user_123",
        "email": "test@example.com",
        "full_name": "Test User",
        "role": "admin",
        "active": False
    }])
    
    success = login("test@example.com", "password")
    assert success is False
    assert mock_streamlit_session_state.get("authenticated", False) is False
    supabase_mock.auth.sign_out.assert_called_once()

def test_login_failure(supabase_mock, mock_streamlit_session_state):
    supabase_mock.auth.sign_in_with_password.side_effect = Exception("Invalid login credentials")
    
    success = login("test@example.com", "wrongpassword")
    assert success is False
    assert mock_streamlit_session_state.get("authenticated", False) is False

def test_register_success(supabase_mock, mock_streamlit_session_state):
    mock_user = MagicMock()
    mock_user.id = "user_new"
    res = MagicMock()
    res.user = mock_user
    res.session = None # Requires email confirmation
    supabase_mock.auth.sign_up.return_value = res
    
    success = register("new@example.com", "password", "New User")
    assert success is False # Because confirmation is required (session=None)
    supabase_mock.auth.sign_up.assert_called_once()

def test_logout(supabase_mock, mock_streamlit_session_state):
    mock_streamlit_session_state.authenticated = True
    mock_streamlit_session_state.user = {"id": "1"}
    
    logout()
    
    assert mock_streamlit_session_state.authenticated is False
    assert mock_streamlit_session_state.user is None
    supabase_mock.auth.sign_out.assert_called_once()
    st.rerun.assert_called_once()

def test_check_permission(mock_streamlit_session_state):
    mock_streamlit_session_state.user = {"role": "admin"}
    assert check_permission(["admin", "editor"]) is True
    assert check_permission(["operator"]) is False
    
    mock_streamlit_session_state.user = None
    assert check_permission(["admin"]) is False

def test_require_auth_granted(mock_streamlit_session_state):
    mock_streamlit_session_state.authenticated = True
    require_auth()
    st.warning.assert_not_called()
    st.stop.assert_not_called()

def test_require_auth_denied(mock_streamlit_session_state):
    mock_streamlit_session_state.authenticated = False
    require_auth()
    st.warning.assert_called_once()
    st.stop.assert_called_once()
