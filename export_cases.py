"""python export_cases.py -> runs the agent on all benchmark cases, writes them to the graph, saves submission/answers/*.json"""
from app import ST, T, OUT
import agent as A
rows = A.run_export(ST, T, OUT); print(f"{len(rows)} cases exported to {OUT}; written to graph ({ST.name}): {sum(r['written_to_graph'] for r in rows)}")
