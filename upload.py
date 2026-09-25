"""
Turns a user-uploaded CSV into the same in-memory dataset shape used by
data.synthetic() / data.load_hhgoa(), so it can be dropped straight into
graph.build_from_dataset() -> LocalStore with no other code changes.

Kept fast on purpose: reads directly from the upload stream (no temp file),
uses vectorized pandas/numpy (the same velocity-window trick as
data.load_hhgoa), and caps rows so a huge accidental upload still responds
quickly instead of hanging the request.
"""
import re
import numpy as np
import pandas as pd

from data import PATTERNS, POLICIES, is_fraud

MAX_ROWS = 200_000

# FraudX investigation schema: what an uploaded CSV must / may contain.
REQUIRED_ALIASES = {
    "transaction_id": ["transaction_id", "transactionid", "tx_id", "txn_id", "id"],
    "customer_id": ["customer_id", "customerid", "cust_id", "cust", "account_id"],
    "amount": ["amount", "amt", "transaction_amount", "transactionamt", "value"],
    "timestamp": ["timestamp", "ts", "transaction_dt", "transactiondt", "date", "datetime", "time"],
}
OPTIONAL_ALIASES = {
    "card_id": ["card_id", "cardid", "card", "card1"],
    "device_id": ["device_id", "deviceid", "device", "deviceinfo"],
    "risk_score": ["risk_score", "bank_risk_score", "fraud_score", "riskscore", "bank_risk"],
    "outcome": ["outcome", "resolution", "label", "is_fraud", "status", "decision"],
}
REQUIRED_SCHEMA_HINT = "Transaction_ID, Customer_ID, Amount, Timestamp (Card_ID, Device_ID, Risk_Score, Outcome optional)"


class SchemaError(ValueError):
    pass


def _find(columns, *aliases):
    low = {re.sub(r"\s+", "_", c.strip().lower()): c for c in columns}
    for a in aliases:
        if a in low:
            return low[a]
    return None


def validate_columns(df):
    """Returns (resolved: {key: actual_column_name}, missing: [key, ...])."""
    resolved, missing = {}, []
    for key, aliases in REQUIRED_ALIASES.items():
        col = _find(df.columns, *aliases)
        if col is None:
            missing.append(key)
        else:
            resolved[key] = col
    for key, aliases in OPTIONAL_ALIASES.items():
        col = _find(df.columns, *aliases)
        if col is not None:
            resolved[key] = col
    return resolved, missing


def _slug(series):
    return series.astype(str).str.strip().str.replace(r"\W+", "_", regex=True)


def build_dataset_from_csv(file_storage):
    """file_storage: a Flask FileStorage (request.files['file']).
    Returns (dataset_dict, summary_dict). Raises SchemaError on bad input."""
    filename = getattr(file_storage, "filename", "") or "upload.csv"
    if not filename.lower().endswith(".csv"):
        raise SchemaError("Please upload a .csv file.")

    try:
        df = pd.read_csv(file_storage.stream, nrows=MAX_ROWS)
    except Exception as e:
        raise SchemaError(f"Could not parse this file as CSV ({type(e).__name__}: {str(e)[:150]}).")

    if df.empty or len(df.columns) < 2:
        raise SchemaError("The CSV file is empty or unreadable.")

    resolved, missing = validate_columns(df)
    if missing:
        raise SchemaError(
            "Unsupported dataset format. Missing required column(s): " + ", ".join(missing) +
            ". Expected the FraudX investigation schema: " + REQUIRED_SCHEMA_HINT + "."
        )

    out = pd.DataFrame()
    out["id"] = "TX_" + _slug(df[resolved["transaction_id"]])
    out["cust"] = "CU_" + _slug(df[resolved["customer_id"]])
    out["amt"] = pd.to_numeric(df[resolved["amount"]], errors="coerce").fillna(0.0)

    ts_raw = df[resolved["timestamp"]]
    ts_num = pd.to_numeric(ts_raw, errors="coerce")
    if ts_num.notna().mean() > 0.9:
        out["ts"] = ts_num.fillna(0.0)
    else:
        parsed = pd.to_datetime(ts_raw, errors="coerce")
        base = parsed.min()
        out["ts"] = (parsed - base).dt.total_seconds().fillna(0.0)

    out["card"] = ("CD_" + _slug(df[resolved["card_id"]])) if "card_id" in resolved else out["cust"].str.replace("CU_", "CD_", regex=False)
    out["dev"] = ("DV_" + _slug(df[resolved["device_id"]])) if "device_id" in resolved else None
    out["fails"] = 0

    # de-dupe transaction ids (keep first) so downstream dict-keying by id is safe
    out = out.drop_duplicates(subset="id").reset_index(drop=True)
    out = out.sort_values(["cust", "ts"]).reset_index(drop=True)

    # velocity: transactions per customer in the preceding 3600s window (vectorized)
    ts = out.ts.values
    vel = np.zeros(len(out), dtype=int)
    for idx in out.groupby("cust").indices.values():
        t = ts[idx]
        vel[idx] = np.arange(len(idx)) - np.searchsorted(t, t - 3600, side="left")
    out["vel"] = vel
    out["new_dev"] = (out.dev.notna() & ~out.duplicated(["cust", "dev"])).astype(int)

    if "risk_score" in resolved:
        out["bank_risk"] = pd.to_numeric(df.loc[out.index, resolved["risk_score"]], errors="coerce").fillna(0.0).clip(0, 1)
    else:
        # no risk score supplied: derive a light heuristic so the demo still has something to rank by
        z = out.groupby("cust").amt.transform(lambda s: (s - s.mean()) / (s.std() or 1)).abs().clip(0, 3) / 3
        out["bank_risk"] = (0.12 + 0.5 * z.fillna(0) + 0.15 * (out["vel"] >= 3)).clip(0, 0.97).round(2)

    if out.dev.isna().all():
        # no device column: give every customer a synthetic primary device so device-fan-out
        # analysis still has something to traverse
        out["dev"] = "DV_" + out["cust"].str.replace("CU_", "", regex=False)

    customers = {}
    agg = out.groupby("cust").amt.agg(["mean", "std", "count"]).fillna(0)
    for c, grp in out.groupby("cust"):
        r = agg.loc[c]
        customers[c] = dict(
            id=c, mean=round(float(r["mean"]), 2), std=round(float(r["std"]), 2),
            n_tx=int(r["count"]), card=grp.card.iloc[0],
            acct="AC_" + c[3:], devices=set(grp.dev.dropna()) or {f"DV_{c}"},
        )

    n = len(out)
    bench_n = min(20, max(3, n // 20)) if n >= 5 else n
    ranked = out.sort_values("bank_risk", ascending=False)
    bench_rows = ranked.head(bench_n)
    bench = [dict(id=f"HHG-U{i+1:03d}", tx_id=row["id"], trigger="Risk score")
              for i, (_, row) in enumerate(bench_rows.iterrows())]
    bench_tx_ids = {b["tx_id"] for b in bench}

    hist = []
    if "outcome" in resolved:
        oc = df.loc[out.index, resolved["outcome"]].astype(str).values
        cust_by_id = dict(zip(out["id"], out["cust"]))
        j = 0
        for tid, o in zip(out["id"], oc):
            if tid in bench_tx_ids or j >= 300:
                continue
            hist.append(dict(
                id=f"H-U{j+1:04d}", cust=cust_by_id[tid], tx_id=tid, pattern="",
                outcome="Confirmed fraud" if is_fraud(o) else "Cleared",
                summary=f"Historical case ({o})", is_benchmark=False, closed=True, status="Closed",
            ))
            j += 1

    dataset = dict(
        source=f"Uploaded CSV: {filename}", customers=customers, txs=out.to_dict("records"),
        hist=hist, bench=bench, patterns=list(PATTERNS), policies=list(POLICIES),
    )
    summary = dict(
        filename=filename, transactions=n, customers=len(customers),
        devices=int(out["dev"].nunique(dropna=True)), benchmark_cases=len(bench),
        historical_cases=len(hist), had_risk_score="risk_score" in resolved,
        had_device_id="device_id" in resolved, had_outcome="outcome" in resolved,
        truncated=n >= MAX_ROWS,
    )
    return dataset, summary
