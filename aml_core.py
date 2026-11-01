"""Lõi phân tích NovaAML: tải dữ liệu IBM AML từ Kaggle, đặc trưng đồ thị, chấm điểm rủi ro.

Dùng chung cho app.py (Streamlit) và notebooks/01_aml_graph_analysis.ipynb.
Ngưỡng và trọng số được khoá trước khi đánh giá — xem log/plans/2026-11-01_aml-streamlit-vn.md.
Đổi các hằng số bên dưới là một phân tích mới, cần ghi lý do.
"""
from __future__ import annotations

import json
from itertools import islice
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
from scipy import sparse

KAGGLE_DATASET = "ealtman2019/ibm-transactions-for-anti-money-laundering-aml"
VARIANT = "HI-Small"  # HI = tỷ lệ rửa tiền cao; LI-Small cho bối cảnh thực tế hơn

ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "data" / "processed"
DECISIONS = ROOT / "data" / "decisions.csv"

# ---------- Giả định quy đổi và ngưỡng Việt Nam ----------
USD_VND = 26_000                # tỷ giá giả định, chỉnh khi cần
LARGE_VALUE_VND = 400e6         # GD giá trị lớn phải báo cáo (QĐ 11/2023/QĐ-TTg)
STRUCT_LOW_VND = 340e6          # vùng "sát ngưỡng": [340, 400) triệu

# ---------- Tham số bộ phát hiện (khoá trước) ----------
WINDOW_DAYS = 3                 # cửa sổ 72h, tính theo khối 3 ngày
FAN_MIN = 5                     # ≥5 đối tác khác nhau trong cửa sổ
STRUCT_MIN = 3                  # ≥3 GD sát ngưỡng trong cửa sổ
PASS_DAYS = 2                   # chuyển tiếp nhanh: vào ≈ ra trong 48h
PASS_RATIO = (0.9, 1.1)
PASS_MIN_VND = 100e6
CYCLE_MAX_LEN = 6
CYCLE_WINDOW_DAYS = 7
CYCLE_HUB_DEGREE = 50           # bỏ tài khoản "trung tâm" (doanh nghiệp, quỹ) khỏi tìm chu trình
CYCLE_CAP = 200_000             # trần số chu trình liệt kê mỗi thành phần liên thông mạnh

WEIGHTS = {
    "fan_out": 20, "fan_in": 20, "cycle": 25,
    "pass_through": 15, "structuring": 15, "cross_currency": 5,
}
ALERT_THRESHOLD = 50

# ---------- Lớp SIMO mô phỏng ----------
SIMO_SEED_SHARE = 0.10          # 10% tài khoản rửa tiền đã bị NH khác báo lên SIMO
SIMO_NOISE_SHARE = 0.0005       # và một ít tài khoản sạch bị báo nhầm
SIMO_BOOST = {"hit": 25, "near": 10}
SEED = 2026

FLAG_LABELS = {
    "fan_out": "Rải tiền (fan-out)",
    "fan_in": "Gom tiền (fan-in)",
    "cycle": "Vòng tròn khép kín",
    "pass_through": "Chuyển tiếp nhanh",
    "structuring": "Chia nhỏ sát ngưỡng 400 triệu",
    "cross_currency": "Đổi tiền tệ / tài sản mã hoá",
}
FORMAT_VI = {
    "Cash": "Tiền mặt", "Wire": "Điện chuyển tiền", "ACH": "Chuyển khoản tự động",
    "Cheque": "Séc", "Credit Card": "Thẻ tín dụng", "Reinvestment": "Tái đầu tư",
    "Bitcoin": "Bitcoin",
}

RAW_COLUMNS = [
    "ts", "from_bank", "from_acct", "to_bank", "to_acct", "amt_recv", "cur_recv",
    "amt_paid", "cur_paid", "fmt", "is_laundering",
]


# ---------- Tải dữ liệu ----------
def download_raw(variant: str = VARIANT) -> tuple[Path, Path]:
    """Tải file giao dịch và file mẫu hình từ Kaggle (công khai, không cần API key)."""
    import kagglehub

    trans = kagglehub.dataset_download(KAGGLE_DATASET, path=f"{variant}_Trans.csv")
    patterns = kagglehub.dataset_download(KAGGLE_DATASET, path=f"{variant}_Patterns.txt")
    return Path(trans), Path(patterns)


def load_transactions(path: Path) -> pd.DataFrame:
    df = pd.read_csv(
        path, header=0, names=RAW_COLUMNS,
        dtype={"from_bank": str, "from_acct": str, "to_bank": str, "to_acct": str,
               "cur_recv": "category", "cur_paid": "category", "fmt": "category",
               "is_laundering": "int8"},
    )
    df["ts"] = pd.to_datetime(df["ts"], format="%Y/%m/%d %H:%M")
    return df


def parse_patterns(path: Path) -> pd.DataFrame:
    """Đọc file *_Patterns.txt thành bảng GD có mã vụ và loại mẫu hình."""
    rows, attempt, kind = [], -1, None
    for line in Path(path).read_text().splitlines():
        if line.startswith("BEGIN"):
            attempt += 1
            kind = line.split(" - ", 1)[1].split(":")[0].strip()
        elif line.startswith("END") or not line.strip():
            continue
        else:
            p = line.split(",")
            rows.append((attempt, kind, p[0], p[1], p[2], p[3], p[4]))
    pat = pd.DataFrame(rows, columns=["attempt", "pattern", "ts", "from_bank", "from_acct",
                                      "to_bank", "to_acct"])
    pat["ts"] = pd.to_datetime(pat["ts"], format="%Y/%m/%d %H:%M")
    return pat


def usd_rates(df: pd.DataFrame) -> dict[str, float]:
    """Tỷ giá ngầm định trong dữ liệu: giá trị 1 đơn vị tiền tệ tính bằng USD."""
    x = df[(df.cur_paid == "US Dollar") & (df.amt_paid > 0)]
    per_usd = (x.amt_recv / x.amt_paid).groupby(x.cur_recv, observed=True).median()
    rates = (1 / per_usd).to_dict()
    rates["US Dollar"] = 1.0
    return {str(k): float(v) for k, v in rates.items()}


def add_vnd(df: pd.DataFrame, rates: dict[str, float]) -> pd.DataFrame:
    df["amt_vnd"] = df.amt_paid * df.cur_paid.astype(str).map(rates).astype(float) * USD_VND
    return df


# ---------- Đặc trưng theo tài khoản ----------
def _bins(ts: pd.Series, t0: pd.Timestamp, days: float, offset: float = 0.0) -> pd.Series:
    return (((ts - t0).dt.total_seconds() / 86400 + offset) // days).astype(int)


def cycle_lengths(df: pd.DataFrame) -> pd.Series:
    """Độ dài chu trình ngắn nhất (2..CYCLE_MAX_LEN) mà mỗi tài khoản nằm trên, trong cửa sổ 7 ngày."""
    e = df.loc[df.from_acct != df.to_acct, ["ts", "from_acct", "to_acct"]]
    deg = pd.concat([e.from_acct, e.to_acct]).value_counts()
    hubs = deg.index[deg > CYCLE_HUB_DEGREE]
    e = e[~e.from_acct.isin(hubs) & ~e.to_acct.isin(hubs)]
    t0 = e.ts.min()
    found: dict[str, int] = {}
    for offset in (0.0, CYCLE_WINDOW_DAYS / 2):
        for _, part in e.groupby(_bins(e.ts, t0, CYCLE_WINDOW_DAYS, offset)):
            G = nx.DiGraph()
            G.add_edges_from(part[["from_acct", "to_acct"]].drop_duplicates()
                             .itertuples(index=False, name=None))
            for comp in nx.strongly_connected_components(G):
                if len(comp) < 2:
                    continue
                cycles = nx.simple_cycles(G.subgraph(comp), length_bound=CYCLE_MAX_LEN)
                for cyc in islice(cycles, CYCLE_CAP):
                    for a in cyc:
                        found[a] = min(found.get(a, 99), len(cyc))
    return pd.Series(found, name="cycle_len", dtype="float")


def account_features(df: pd.DataFrame) -> pd.DataFrame:
    t0 = df.ts.min()
    ext = df[df.from_acct != df.to_acct].copy()
    ext["bin"] = _bins(ext.ts, t0, WINDOW_DAYS)

    acc = pd.DataFrame({
        "bank": pd.concat([df[["from_acct", "from_bank"]].set_axis(["a", "b"], axis=1),
                           df[["to_acct", "to_bank"]].set_axis(["a", "b"], axis=1)])
                .drop_duplicates("a").set_index("a")["b"],
    })
    acc["out_n"] = ext.groupby("from_acct").size()
    acc["in_n"] = ext.groupby("to_acct").size()
    acc["out_vnd"] = ext.groupby("from_acct").amt_vnd.sum()
    acc["in_vnd"] = ext.groupby("to_acct").amt_vnd.sum()
    acc["fan_out_max"] = ext.groupby(["from_acct", "bin"]).to_acct.nunique().groupby(level=0).max()
    acc["fan_in_max"] = ext.groupby(["to_acct", "bin"]).from_acct.nunique().groupby(level=0).max()

    band = ext[(ext.amt_vnd >= STRUCT_LOW_VND) & (ext.amt_vnd < LARGE_VALUE_VND)]
    acc["struct_max"] = band.groupby(["from_acct", "bin"]).size().groupby(level=0).max()
    acc["large_n"] = df[df.amt_vnd >= LARGE_VALUE_VND].groupby("from_acct").size()

    # Chuyển tiếp nhanh: trong cùng khối 48h, tiền ra / tiền vào nằm trong [0.9, 1.1]
    pb = _bins(ext.ts, t0, PASS_DAYS)
    vin = ext.groupby([ext.to_acct, pb]).amt_vnd.sum()
    vout = ext.groupby([ext.from_acct, pb]).amt_vnd.sum()
    flow = pd.concat([vin.rename("vin"), vout.rename("vout")], axis=1).dropna()
    ratio = flow.vout / flow.vin
    passing = flow[(ratio.between(*PASS_RATIO)) & (flow.vin >= PASS_MIN_VND)]
    acc["pass_through"] = acc.index.isin(passing.index.get_level_values(0))

    xc = df[(df.cur_paid.astype(str) != df.cur_recv.astype(str))
            | (df.cur_paid == "Bitcoin") | (df.cur_recv == "Bitcoin")]
    acc["cross_currency"] = acc.index.isin(pd.concat([xc.from_acct, xc.to_acct]).unique())

    acc["cycle_len"] = cycle_lengths(df)

    counts = ["out_n", "in_n", "out_vnd", "in_vnd", "fan_out_max", "fan_in_max",
              "struct_max", "large_n"]
    acc[counts] = acc[counts].fillna(0)
    acc.index.name = "account"
    return acc


def score(acc: pd.DataFrame) -> pd.DataFrame:
    """Điểm 0–100 = Σ trọng số × mức độ của từng dấu hiệu (mỗi mức trong [0, 1])."""
    s = pd.DataFrame(index=acc.index)
    s["fan_out"] = ((acc.fan_out_max - 1) / (FAN_MIN - 1)).clip(0, 1)
    s["fan_in"] = ((acc.fan_in_max - 1) / (FAN_MIN - 1)).clip(0, 1)
    s["cycle"] = acc.cycle_len.notna().astype(float)
    s["pass_through"] = acc.pass_through.astype(float)
    s["structuring"] = (acc.struct_max / STRUCT_MIN).clip(0, 1)
    s["cross_currency"] = acc.cross_currency.astype(float)
    out = acc.copy()
    for k, w in WEIGHTS.items():
        out[f"s_{k}"] = s[k]
    out["risk"] = sum(s[k] * w for k, w in WEIGHTS.items()).round(1)
    out["signals"] = s.ge(1).apply(lambda r: [k for k in WEIGHTS if r[k]], axis=1)
    return out


def degree_baseline(acc: pd.DataFrame) -> pd.Series:
    """Điểm của demo1.py gốc (chỉ bậc + tổng tiền), để so sánh."""
    deg = acc.out_n + acc.in_n
    return 100 * (0.6 * deg.rank(pct=True) + 0.4 * acc.out_vnd.rank(pct=True))


def account_labels(df: pd.DataFrame) -> pd.Series:
    lab = df[df.is_laundering == 1]
    return pd.Index(pd.concat([lab.from_acct, lab.to_acct]).unique())


# ---------- SIMO mô phỏng ----------
def simulate_simo(acc: pd.DataFrame, laundering: pd.Index) -> pd.Index:
    rng = np.random.default_rng(SEED)
    bad = acc.index[acc.index.isin(laundering)]
    good = acc.index[~acc.index.isin(laundering)]
    pick_bad = rng.choice(bad, int(len(bad) * SIMO_SEED_SHARE), replace=False)
    pick_good = rng.choice(good, int(len(good) * SIMO_NOISE_SHARE), replace=False)
    return pd.Index(np.concatenate([pick_bad, pick_good]))


def simo_overlay(df: pd.DataFrame, acc: pd.DataFrame, simo: pd.Index) -> pd.DataFrame:
    """Đánh dấu tài khoản trùng SIMO hoặc cách tài khoản SIMO tối đa 2 bước giao dịch."""
    idx = pd.Index(acc.index)
    ext = df[df.from_acct != df.to_acct]
    i, j = idx.get_indexer(ext.from_acct), idx.get_indexer(ext.to_acct)
    n = len(idx)
    A = sparse.coo_matrix((np.ones(len(i), dtype=np.int8), (i, j)), shape=(n, n)).tocsr()
    A = ((A + A.T) > 0).astype(np.int8)
    hit = idx.isin(simo).astype(np.int8)
    one = (A @ hit) > 0
    two = (A @ one.astype(np.int8)) > 0
    out = acc.copy()
    out["simo_hit"] = hit.astype(bool)
    out["simo_near"] = (one | two) & ~out.simo_hit
    out["priority"] = (out.risk + SIMO_BOOST["hit"] * out.simo_hit
                       + SIMO_BOOST["near"] * out.simo_near).clip(upper=100).round(1)
    return out


# ---------- Tập con cho ứng dụng ----------
def demo_subset(df: pd.DataFrame, acc: pd.DataFrame, top_n: int = 3000) -> pd.DataFrame:
    """GD của mọi tài khoản vượt ngưỡng (ít nhất top_n tài khoản) và mọi GD có nhãn, để vẽ mạng lưới."""
    n = max(top_n, int((acc.priority >= ALERT_THRESHOLD).sum()))
    top = acc.nlargest(n, "priority").index
    keep = df.from_acct.isin(top) | df.to_acct.isin(top) | (df.is_laundering == 1)
    return df[keep].reset_index(drop=True)


def prepare(variant: str = VARIANT, top_n: int = 3000) -> dict:
    """Tải + xử lý một lần, ghi parquet vào data/processed/. Trả về metadata."""
    PROCESSED.mkdir(parents=True, exist_ok=True)
    trans_path, pat_path = download_raw(variant)
    df = load_transactions(trans_path)
    rates = usd_rates(df)
    df = add_vnd(df, rates)
    acc = score(account_features(df))
    laundering = account_labels(df)
    acc["is_laundering"] = acc.index.isin(laundering)
    simo = simulate_simo(acc, laundering)
    acc = simo_overlay(df, acc, simo)

    pat = parse_patterns(pat_path)
    first = pd.concat([pat[["from_acct", "pattern"]].set_axis(["a", "p"], axis=1),
                       pat[["to_acct", "pattern"]].set_axis(["a", "p"], axis=1)])
    acc["pattern"] = first.drop_duplicates("a").set_index("a").p

    sub = demo_subset(df, acc, top_n)
    acc_out = acc.copy()
    acc_out["signals"] = acc_out["signals"].apply(lambda f: ",".join(f))
    acc_out.reset_index().to_parquet(PROCESSED / "accounts.parquet", index=False)
    sub.to_parquet(PROCESSED / "transactions_demo.parquet", index=False)
    pat.to_parquet(PROCESSED / "patterns.parquet", index=False)

    meta = {
        "variant": variant, "usd_vnd": USD_VND, "rates_usd": rates,
        "n_transactions": int(len(df)), "n_laundering_tx": int(df.is_laundering.sum()),
        "n_accounts": int(len(acc)), "n_simo": int(len(simo)),
        "start": str(df.ts.min()), "end": str(df.ts.max()),
        "home_bank": str(df.from_bank.value_counts().idxmax()),
    }
    (PROCESSED / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return meta


def load_prepared() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    acc = pd.read_parquet(PROCESSED / "accounts.parquet")
    acc["signals"] = acc["signals"].fillna("").apply(lambda s: [f for f in s.split(",") if f])
    tx = pd.read_parquet(PROCESSED / "transactions_demo.parquet")
    meta = json.loads((PROCESSED / "meta.json").read_text())
    return acc, tx, meta


def is_prepared() -> bool:
    return all((PROCESSED / f).exists()
               for f in ("accounts.parquet", "transactions_demo.parquet", "meta.json"))


if __name__ == "__main__":
    print(json.dumps(prepare(), ensure_ascii=False, indent=2))
