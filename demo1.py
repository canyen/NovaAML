import streamlit as st
import pandas as pd
import numpy as np
import networkx as nx
import plotly.graph_objects as go
from datetime import datetime
from pathlib import Path

st.set_page_config(page_title="NovaAML - Demo", layout="wide")

@st.cache_data
def gen_data(seed=42, n_acc=300, n_tx=3000):
    rng = np.random.default_rng(seed)
    accounts = []
    seen_accounts = set()
    while len(accounts) < n_acc:
        account = f"80{rng.integers(0, 16**6):06X}0"
        if account not in seen_accounts:
            accounts.append(account)
            seen_accounts.add(account)

    amount_paid = np.round(rng.lognormal(14, 1, n_tx), 2)
    currencies = ["US Dollar", "Euro", "Yuan", "UK Pound"]
    tx = pd.DataFrame({
        "From Bank": rng.integers(1, 3210, n_tx),
        "From Account": rng.choice(accounts, n_tx),
        "To Bank": rng.integers(1, 3210, n_tx),
        "To Account": rng.choice(accounts, n_tx),
        "Amount Received": amount_paid,
        "Receiving Currency": rng.choice(currencies, n_tx),
        "Amount Paid": amount_paid,
        "Payment Currency": rng.choice(currencies, n_tx),
        "Payment Format": rng.choice(
            ["Cash", "Credit Card", "Wire", "ACH", "Cheque", "Reinvestment"],
            n_tx,
        ),
        "Timestamp": pd.Timestamp("2026-10-01") + pd.to_timedelta(
            rng.integers(0, 30 * 24 * 60, n_tx), unit="m"
        ),
    })

    hub = accounts[0]
    inj = pd.DataFrame([
        {
            "From Bank": 1,
            "From Account": hub,
            "To Bank": 1,
            "To Account": m,
            "Amount Received": 390e6 + i * 1e6,
            "Receiving Currency": "US Dollar",
            "Amount Paid": 390e6 + i * 1e6,
            "Payment Currency": "US Dollar",
            "Payment Format": "Wire",
            "Timestamp": pd.Timestamp("2026-10-15 09:00") + pd.Timedelta(minutes=i),
        }
        for i, m in enumerate(accounts[1:9])
    ])
    tx = pd.concat([tx, inj], ignore_index=True)

    acc = pd.DataFrame(index=accounts)
    acc["out_n"] = tx.groupby("From Account").size()
    acc["in_n"] = tx.groupby("To Account").size()
    acc["out_amt"] = tx.groupby("From Account")["Amount Paid"].sum()
    acc["smurf_n"] = tx[
        (tx["Amount Paid"] > 350e6) & (tx["Amount Paid"] < 400e6)
    ].groupby("From Account").size()
    acc = acc.fillna(0)
    deg = acc["out_n"] + acc["in_n"]
    # Điểm demo: kết hợp bậc, mức chia nhỏ và tổng tiền chuyển đi (thang 0-100)
    acc["risk"] = (100 * (0.5 * deg.rank(pct=True)
                          + 0.3 * acc["smurf_n"].rank(pct=True)
                          + 0.2 * acc["out_amt"].rank(pct=True))).round(1)
    return tx, acc.reset_index().rename(columns={"index": "account"})

def network_fig(tx, acc_id):
    sub = tx[(tx["From Account"] == acc_id) | (tx["To Account"] == acc_id)]
    G = nx.DiGraph()
    G.add_node(acc_id)
    for row in sub[["From Account", "To Account"]].itertuples(index=False, name=None):
        G.add_edge(*row)
    pos = nx.spring_layout(G, seed=1)
    ex, ey = [], []
    for u, v in G.edges():
        ex += [pos[u][0], pos[v][0], None]
        ey += [pos[u][1], pos[v][1], None]
    nodes = list(G.nodes())
    fig = go.Figure([
        go.Scatter(x=ex, y=ey, mode="lines", line=dict(width=1, color="#999"), hoverinfo="none"),
        go.Scatter(x=[pos[n][0] for n in nodes], y=[pos[n][1] for n in nodes],
                   mode="markers+text", text=nodes, textposition="top center",
                   marker=dict(size=[18 if n == acc_id else 10 for n in nodes],
                               color=["#d62728" if n == acc_id else "#1f77b4" for n in nodes])),
    ])
    fig.update_layout(showlegend=False, height=420, margin=dict(l=0, r=0, t=0, b=0),
                      xaxis_visible=False, yaxis_visible=False)
    return fig

def save_decision(account, ket_luan, ghi_chu):
    rec = pd.DataFrame([{
        "account": account, "ket_luan": ket_luan, "ghi_chu": ghi_chu,
        "thoi_diem": datetime.now().isoformat(timespec="seconds"),
        "nguoi_quyet_dinh": "chuyen_vien_demo",
    }])
    rec.to_csv("decisions.csv", mode="a", header=not Path("decisions.csv").exists(), index=False)

# ---------- Giao diện ----------
st.title("NovaAML: Hỗ trợ điều tra theo tài khoản")

tx, acc = gen_data()
min_risk = st.sidebar.slider("Ngưỡng điểm rủi ro tối thiểu", 0, 100, 70)
queue = acc[acc.risk >= min_risk].sort_values("risk", ascending=False)

col1, col2 = st.columns([1, 2])
with col1:
    st.subheader(f"Hàng đợi cảnh báo ({len(queue)} tài khoản)")
    st.dataframe(queue[["account", "risk", "out_n", "in_n", "smurf_n"]], hide_index=True)
    options = queue.account.tolist() or acc.account.tolist()
    sel = st.selectbox("Chọn tài khoản để điều tra", options)

with col2:
    row = acc[acc.account == sel].iloc[0]
    m1, m2, m3 = st.columns(3)
    m1.metric("Điểm rủi ro", row.risk)
    m2.metric("Giao dịch ra", int(row.out_n))
    m3.metric("Giao dịch vào", int(row.in_n))

    st.markdown("**Mạng lưới giao dịch quanh tài khoản**")
    st.plotly_chart(network_fig(tx, sel))

    st.markdown("**Giao dịch liên quan (50 gần nhất)**")
    rel = tx[
        (tx["From Account"] == sel) | (tx["To Account"] == sel)
    ].sort_values("Timestamp", ascending=False).head(50)
    st.dataframe(
        rel[
            [
                "From Bank", "From Account", "To Bank", "To Account",
                "Amount Received", "Receiving Currency", "Amount Paid",
                "Payment Currency", "Payment Format",
            ]
        ],
        hide_index=True,
    )

    st.markdown("**Quyết định của chuyên viên**")
    with st.form("decision"):
        ket_luan = st.radio("Kết luận", ["Cần theo dõi", "Chuyển điều tra sâu", "Không đáng ngờ"], horizontal=True)
        ghi_chu = st.text_area("Ghi chú lý do")
        if st.form_submit_button("Lưu quyết định"):
            save_decision(sel, ket_luan, ghi_chu)
            st.success("Đã lưu vào decisions.csv")

    if Path("decisions.csv").exists():
        st.markdown("**Nhật ký quyết định**")
        st.dataframe(pd.read_csv("decisions.csv"), hide_index=True)