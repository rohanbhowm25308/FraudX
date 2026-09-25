import os
from data import synthetic, load_hhgoa

def build_store():
    """TigerGraph if TG_HOST is set and reachable (with data loaded); otherwise the local in-memory graph."""
    reason = ""
    if os.getenv("TG_HOST"):
        try:
            from .tg import TigerGraphStore
            st = TigerGraphStore(); st.ping()
            if st.bench_list(): return st
            reason = "TigerGraph is reachable but empty - run: python ingest.py"
        except Exception as e: reason = f"TigerGraph unavailable ({type(e).__name__}: {str(e)[:120]}) - using local graph"
    from .local import LocalStore
    d = os.getenv("DATA_DIR")
    ds = load_hhgoa(d) if d else synthetic()
    st = LocalStore(ds, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory.json")); st.note = reason
    return st
