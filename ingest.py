"""Load data into TigerGraph.   python ingest.py --synthetic     (demo data, verifies your TigerGraph connection)
                               python ingest.py --data ./HHGOA_IEEE   (the official dataset)"""
import argparse
from dotenv import load_dotenv; load_dotenv()
from data import synthetic, load_hhgoa
from graph.tg import TigerGraphStore
p = argparse.ArgumentParser(); p.add_argument("--data"); p.add_argument("--synthetic", action="store_true"); p.add_argument("--skip-schema", action="store_true"); a = p.parse_args()
ds = load_hhgoa(a.data, full=True) if a.data else synthetic()
st = TigerGraphStore(); print("Connected to TigerGraph")
if not a.skip_schema: st.install(); print("Schema + queries installed")
st.ingest(ds); print(f"Ingested {len(ds['customers'])} customers, {len(ds['txs'])} transactions, {len(ds['bench'])} benchmark cases, {len(ds['hist'])} historical cases from {ds['source']}")
