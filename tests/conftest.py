import pytest
from unittest.mock import MagicMock, patch
import streamlit as st

# --- STREAMLIT SESSION STATE MOCK ---
class MockSessionState(dict):
    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(item)
    def __setattr__(self, key, value):
        self[key] = value
    def __delattr__(self, item):
        try:
            del self[item]
        except KeyError:
            raise AttributeError(item)

# Create a global mock session state
session_state_mock = MockSessionState()

# Mock caching decorators of streamlit BEFORE importing other modules
st.cache_resource = lambda func=None, **kwargs: func if func else lambda f: f
st.cache_data = lambda func=None, **kwargs: func if func else lambda f: f

@pytest.fixture(autouse=True)
def mock_streamlit_session_state(monkeypatch):
    session_state_mock.clear()
    monkeypatch.setattr(st, "session_state", session_state_mock)
    
    # Mock rerun, stop, and status elements to prevent test execution halts
    monkeypatch.setattr(st, "rerun", MagicMock())
    monkeypatch.setattr(st, "stop", MagicMock())
    monkeypatch.setattr(st, "error", MagicMock())
    monkeypatch.setattr(st, "success", MagicMock())
    monkeypatch.setattr(st, "warning", MagicMock())
    monkeypatch.setattr(st, "info", MagicMock())
    monkeypatch.setattr(st, "sidebar", MagicMock())
    
    return session_state_mock


# --- SUPABASE MOCK ---
class MockTable:
    def __init__(self, data=None):
        self.data = data if data is not None else []
        self._eq_filters = {}
        self._order_by = None
        self._limit = None

    def select(self, *args, **kwargs): return self
    
    def eq(self, field, value, *args, **kwargs):
        self._eq_filters[field] = value
        return self
        
    def neq(self, *args, **kwargs): return self
    def gt(self, *args, **kwargs): return self
    def lt(self, *args, **kwargs): return self
    def order(self, field, desc=False, *args, **kwargs):
        self._order_by = (field, desc)
        return self
    def limit(self, limit_val, *args, **kwargs):
        self._limit = limit_val
        return self
    def desc(self, *args, **kwargs): return self
    
    def insert(self, data, *args, **kwargs):
        import copy
        inserted = copy.deepcopy(data)
        inserted_list = inserted if isinstance(inserted, list) else [inserted]
        for item in inserted_list:
            if isinstance(item, dict) and "id" not in item:
                item["id"] = "mock-id-123"
            self.data.append(item)
        return MockTable(inserted_list)
        
    def update(self, data, *args, **kwargs):
        import copy
        updated_patch = copy.deepcopy(data)
        updated_list = []
        for item in self.data:
            match = True
            for field, val in self._eq_filters.items():
                if str(item.get(field)) != str(val):
                    match = False
                    break
            if match:
                item.update(updated_patch)
                updated_list.append(item)
        # If no filters were set, update all items
        if not self._eq_filters and self.data:
            for item in self.data:
                item.update(updated_patch)
                updated_list.append(item)
        self._eq_filters = {}
        return MockTable(updated_list)
        
    def delete(self, *args, **kwargs):
        remaining = []
        deleted = []
        for item in self.data:
            match = True
            for field, val in self._eq_filters.items():
                if str(item.get(field)) != str(val):
                    match = False
                    break
            if match:
                deleted.append(item)
            else:
                remaining.append(item)
        self.data.clear()
        self.data.extend(remaining)
        self._eq_filters = {}
        return MockTable(deleted)
        
    def execute(self):
        filtered = list(self.data)
        for field, value in self._eq_filters.items():
            filtered = [x for x in filtered if str(x.get(field)) == str(value)]
        self._eq_filters = {}
        
        if self._order_by:
            field, desc = self._order_by
            def get_val(x):
                val = x.get(field)
                return val if val is not None else ""
            filtered = sorted(filtered, key=get_val, reverse=desc)
            self._order_by = None
            
        if self._limit is not None:
            filtered = filtered[:self._limit]
            self._limit = None
            
        result = MagicMock()
        result.data = filtered
        return result

class MockSupabaseClient:
    def __init__(self):
        self.mock_tables = {}
        self.auth = MagicMock()
        self.storage = MagicMock()

    def table(self, table_name):
        if table_name not in self.mock_tables:
            self.mock_tables[table_name] = MockTable([])
        return self.mock_tables[table_name]

    def set_table_data(self, table_name, data):
        self.mock_tables[table_name] = MockTable(data)


@pytest.fixture(autouse=True)
def supabase_mock(monkeypatch):
    client = MockSupabaseClient()
    
    # Force import of all service modules so we can patch them
    import lib.supabase_client
    import lib.db
    import lib.auth
    import lib.payroll_service
    import lib.quotation_service
    import lib.audit_service
    import lib.excel_importer
    import lib.document_service
    
    # Patch get_supabase_client in all imported modules
    modules = [
        lib.supabase_client, lib.db, lib.auth, lib.payroll_service,
        lib.quotation_service, lib.audit_service, lib.excel_importer,
        lib.document_service
    ]
    
    for module in modules:
        if hasattr(module, "get_supabase_client"):
            monkeypatch.setattr(module, "get_supabase_client", lambda: client)
            
    return client
