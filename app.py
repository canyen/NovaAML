"""NovaAML — lớp phân tích mạng lưới giao dịch đặt trên TMS lõi và SIMO (bản demo).

Chạy:  streamlit run app.py
Lần đầu app sẽ tự tải dữ liệu IBM AML từ Kaggle (hoặc chạy trước: python prepare_data.py).
Phát triển từ demo1.py: giữ luồng hàng đợi → điều tra → quyết định, thay dữ liệu sinh ngẫu nhiên
bằng dữ liệu Kaggle và điểm rủi ro theo mẫu hình (aml_core.py).
"""
from datetime import datetime
from html import escape

import networkx as nx
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import aml_core as core

st.set_page_config(page_title="NovaAML", layout="wide", initial_sidebar_state="expanded")

INK, MUTED, ACCENT, DANGER, GRID = "#141716", "#5c6461", "#0b6e5f", "#b42318", "#e6e9e7"
FONT = "Be Vietnam Pro, system-ui, sans-serif"
QUEUE_ROWS = 1000      # số dòng tối đa gửi xuống trình duyệt ở hàng đợi
CASE_OPTIONS = 3000    # số tài khoản trong ô chọn hồ sơ

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600&display=swap');
html, body, [class*="css"] {{ font-family: {FONT}; }}
h1 {{ font-size: 26px !important; font-weight: 600 !important; letter-spacing: -0.01em; padding-bottom: 0 !important; }}
h3 {{ font-size: 16px !important; font-weight: 600 !important; }}
.block-container {{ padding-top: 2.2rem; max-width: 1440px; }}
::selection {{ background: #cfe6e0; }}
.lead {{ color: {INK}; font-size: 15px; margin: 2px 0 18px; max-width: 75ch; }}
.lead b {{ font-weight: 600; }}
.kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid {GRID};
         border-radius: 6px; background: #fff; margin-bottom: 20px; }}
.kpis > div {{ padding: 14px 18px; border-left: 1px solid {GRID}; }}
.kpis > div:first-child {{ border-left: 0; }}
.kpis .l {{ color: {MUTED}; font-size: 13px; }}
.kpis .v {{ color: {INK}; font-size: 24px; font-weight: 500; font-variant-numeric: tabular-nums; }}
.kpis .v small {{ color: {MUTED}; font-size: 13px; font-weight: 400; margin-left: 4px; }}
.kpis .v.lead-fig {{ font-size: 32px; font-weight: 600; }}
.pill {{ display: inline-block; padding: 2px 9px; margin: 0 6px 6px 0; border-radius: 999px;
         font-size: 13px; background: #e4f1ed; color: #07443b; }}
.pill.bad {{ background: #fdecea; color: #7a1a12; }}
.pill.muted {{ background: #eef1ef; color: {MUTED}; }}
.side-meta {{ color: {MUTED}; font-size: 13px; line-height: 1.55; }}
.side-meta b {{ color: {INK}; font-weight: 500; }}
.mark {{ font-size: 20px; font-weight: 600; letter-spacing: -0.02em; color: {INK}; }}
.note {{ color: {MUTED}; font-size: 13px; }}
@media (max-width: 760px) {{ .kpis {{ grid-template-columns: repeat(2, 1fr); }}
  .kpis > div:nth-child(3) {{ border-left: 0; border-top: 1px solid {GRID}; }}
  .kpis > div:nth-child(4) {{ border-top: 1px solid {GRID}; }} }}
</style>
""", unsafe_allow_html=True)


# ---------- Định dạng ----------
def vnd(x: float) -> str:
    """Số tiền kiểu Việt Nam: 1,25 tỷ · 350 triệu · 12.500 đ."""
    if pd.isna(x):
        return "–"
    if abs(x) >= 1e9:
        return f"{x / 1e9:,.2f} tỷ".replace(",", "#").replace(".", ",").replace("#", ".")
    if abs(x) >= 1e6:
        return f"{x / 1e6:,.0f} triệu".replace(",", ".")
    return f"{x:,.0f} đ".replace(",", ".")


def num(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def kpi_strip(items):
    cells = "".join(
        f'<div><div class="l">{escape(l)}</div>'
        f'<div class="v{" lead-fig" if lead else ""}">{v}{f"<small>{escape(u)}</small>" if u else ""}</div></div>'
        for l, v, u, lead in items)
    st.markdown(f'<div class="kpis">{cells}</div>', unsafe_allow_html=True)


def pills(acc_row) -> str:
    out = [f'<span class="pill">{escape(core.FLAG_LABELS[f])}</span>' for f in acc_row.signals]
    if acc_row.simo_hit:
        out.insert(0, '<span class="pill bad">Có trong danh sách SIMO</span>')
    elif acc_row.simo_near:
        out.insert(0, '<span class="pill bad">Cách tài khoản SIMO ≤ 2 bước</span>')
    return "".join(out) or '<span class="pill muted">Chưa có dấu hiệu mẫu hình</span>'


def style_fig(fig, height=380):
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="#fff", plot_bgcolor="#fff",
        font=dict(family=FONT, color=INK, size=12), showlegend=False,
        hoverlabel=dict(bgcolor="#fff", font_family=FONT),
    )
    return fig


# ---------- Dữ liệu ----------
# cache_resource: dữ liệu chỉ đọc, dùng chung cho mọi lần chạy lại mà không sao chép
# (cache_data sao chép ~1,3 s mỗi lần tương tác với bảng 515k tài khoản + 655k GD).
@st.cache_resource(show_spinner="Đang nạp dữ liệu…")
def load():
    acc, tx, meta = core.load_prepared()
    tx = tx[tx.from_acct != tx.to_acct].sort_values("ts", ascending=False).reset_index(drop=True)
    tx["fmt_vi"] = tx.fmt.astype(str).map(core.FORMAT_VI).fillna(tx.fmt.astype(str))
    acc = acc.set_index("account")
    by_from, by_to = tx.groupby("from_acct").indices, tx.groupby("to_acct").indices
    acc["in_app"] = acc.index.isin(by_from.keys() | by_to.keys())
    pool = acc[acc.in_app].sort_values(["priority", "out_vnd"], ascending=False)
    pool["signals_vi"] = pool.signals.apply(lambda f: ", ".join(core.FLAG_LABELS[x] for x in f))
    return acc, tx, meta, by_from, by_to, pool


def rows_of(accounts) -> np.ndarray:
    """Vị trí các GD (đã sắp mới nhất trước) có chạm tới một trong các tài khoản."""
    parts = [ix for a in accounts for ix in (BY_FROM.get(a), BY_TO.get(a)) if ix is not None]
    return np.unique(np.concatenate(parts)) if parts else np.array([], dtype=int)


def load_decisions() -> pd.DataFrame:
    if core.DECISIONS.exists():
        return pd.read_csv(core.DECISIONS, dtype={"account": str})
    return pd.DataFrame(columns=["account", "ket_luan", "ghi_chu", "thoi_diem", "nguoi_quyet_dinh"])


def save_decision(account, ket_luan, ghi_chu, analyst):
    core.DECISIONS.parent.mkdir(parents=True, exist_ok=True)
    rec = pd.DataFrame([{
        "account": account, "ket_luan": ket_luan, "ghi_chu": ghi_chu,
        "thoi_diem": datetime.now().isoformat(timespec="seconds"), "nguoi_quyet_dinh": analyst,
    }])
    rec.to_csv(core.DECISIONS, mode="a", header=not core.DECISIONS.exists(), index=False)


if not core.is_prepared():
    st.title("NovaAML")
    st.markdown(
        '<p class="lead">Chưa có dữ liệu trên máy này. App sẽ tải bộ IBM Transactions for AML '
        f'({core.VARIANT}, khoảng 475 MB) trực tiếp từ Kaggle, không cần tài khoản, rồi tính đặc trưng mạng lưới. '
        'Lần đầu mất khoảng 5–10 phút.</p>', unsafe_allow_html=True)
    if st.button("Tải và xử lý dữ liệu", type="primary"):
        with st.spinner("Đang tải từ Kaggle và tính đặc trưng…"):
            try:
                core.prepare()
            except Exception as e:  # mạng, Kaggle đổi phiên bản, thiếu RAM
                st.error(f"Không xử lý được dữ liệu: {e}. Kiểm tra kết nối mạng rồi thử lại, "
                         "hoặc chạy `python prepare_data.py` để xem lỗi chi tiết.")
                st.stop()
        st.rerun()
    st.stop()

acc, tx, meta, BY_FROM, BY_TO, pool = load()
decisions = load_decisions()
decided = set(decisions.account)

# ---------- Thanh bên ----------
with st.sidebar:
    st.markdown('<div class="mark">NovaAML</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="side-meta">Ngân hàng <b>NH-{meta["home_bank"]}</b> · khối PCRT<br>'
        f'Dữ liệu {num(meta["n_transactions"])} GD, {meta["start"][:10]} → {meta["end"][:10]}<br>'
        f'TMS lõi: đồng bộ cảnh báo <b>mô phỏng</b><br>'
        f'SIMO – NHNN: {num(meta["n_simo"])} tài khoản nghi ngờ <b>mô phỏng</b></div>',
        unsafe_allow_html=True)
    st.write("")
    analyst = st.text_input("Chuyên viên", value=st.session_state.get("analyst", "chuyen_vien_01"))
    st.session_state.analyst = analyst


# ---------- Trang: Hàng đợi ----------
def page_queue():
    st.title("Hàng đợi cảnh báo")
    c1, c2, c3 = st.columns([2, 2, 1.2])
    min_p = c1.slider("Điểm ưu tiên tối thiểu", 0, 100, core.ALERT_THRESHOLD)
    flag_pick = c2.multiselect("Mẫu hình", list(core.FLAG_LABELS), format_func=core.FLAG_LABELS.get,
                               placeholder="Mọi mẫu hình")
    only_simo = c3.toggle("Chỉ liên quan SIMO")
    show_open = c3.toggle("Ẩn đã xử lý", value=True)

    q = pool[pool.priority >= min_p]  # pool đã sắp theo ưu tiên
    if flag_pick:
        q = q[q.signals.apply(lambda f: all(x in f for x in flag_pick))]
    if only_simo:
        q = q[q.simo_hit | q.simo_near]
    n_decided = int(q.index.isin(decided).sum())
    if show_open:
        q = q[~q.index.isin(decided)]

    simo_n = int((q.simo_hit | q.simo_near).sum())
    top_flag = pd.Series([f for fs in q.signals for f in fs]).value_counts()
    finding = (f'<b>{num(len(q))}</b> tài khoản chờ xem xét ở ngưỡng {min_p}; '
               f'<b>{num(simo_n)}</b> trong số đó trùng hoặc giao dịch gần với danh sách SIMO')
    if len(top_flag):
        finding += f'. Dấu hiệu phổ biến nhất: {core.FLAG_LABELS[top_flag.index[0]].lower()} ({num(top_flag.iloc[0])}).'
    st.markdown(f'<p class="lead">{finding}</p>', unsafe_allow_html=True)

    kpi_strip([
        ("Cảnh báo mở", num(len(q)), "tài khoản", True),
        ("Liên quan SIMO", num(simo_n), "tài khoản", False),
        ("Đã có quyết định", num(n_decided), "tài khoản", False),
        ("GD ≥ 400 triệu (TMS đã báo cáo)", num(q.large_n.sum()), "GD", False),
    ])

    if q.empty:
        st.info("Không có tài khoản nào khớp bộ lọc. Hạ điểm ưu tiên tối thiểu hoặc bỏ bớt mẫu hình.")
        return

    shown = q.head(QUEUE_ROWS)
    view = pd.DataFrame({
        "Tài khoản": shown.index,
        "Ngân hàng": "NH-" + shown.bank.values,
        "Ưu tiên": shown.priority.values,
        "Điểm mẫu hình": shown.risk.values,
        "SIMO": np.where(shown.simo_hit, "Trùng", np.where(shown.simo_near, "Gần", "")),
        "Dấu hiệu": shown.signals_vi.values,
        "Tiền ra (triệu)": (shown.out_vnd / 1e6).round(0).values,
        "Tiền vào (triệu)": (shown.in_vnd / 1e6).round(0).values,
    })
    st.markdown("### Danh sách theo mức ưu tiên")
    more = f" Đang hiện {num(QUEUE_ROWS)} tài khoản đầu trên {num(len(q))}; tăng ngưỡng để thu hẹp." if len(q) > QUEUE_ROWS else ""
    st.caption("Chọn một dòng để mở hồ sơ tài khoản. Ưu tiên = điểm mẫu hình + 25 nếu trùng SIMO, "
               f"+10 nếu cách SIMO ≤ 2 bước.{more}")
    ev = st.dataframe(
        view, hide_index=True, width="stretch", height=520, on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Ưu tiên": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f", width="small"),
            "Điểm mẫu hình": st.column_config.NumberColumn(format="%.0f", width="small"),
            "Tiền ra (triệu)": st.column_config.NumberColumn(format="localized"),
            "Tiền vào (triệu)": st.column_config.NumberColumn(format="localized"),
            "Dấu hiệu": st.column_config.TextColumn(width="large"),
        },
    )
    if ev.selection.rows:
        st.session_state.account = view.iloc[ev.selection.rows[0]]["Tài khoản"]
        st.switch_page(PAGES["case"])


# ---------- Trang: Hồ sơ tài khoản ----------
def ego_edges(acc_id: str, hops: int) -> pd.DataFrame:
    nodes, frontier = {acc_id}, {acc_id}
    for _ in range(hops):
        near = tx.iloc[rows_of(frontier)]
        frontier = set(near.from_acct) | set(near.to_acct)
        # giữ mạng lưới đọc được: 25 đối tác lớn nhất mỗi bước
        if len(frontier) > 25:
            amt = pd.concat([near.groupby("from_acct").amt_vnd.sum(), near.groupby("to_acct").amt_vnd.sum()])
            frontier = set(amt.groupby(level=0).sum().nlargest(25).index) | {acc_id}
        nodes |= frontier
    e = tx.iloc[rows_of(nodes)]
    e = e[e.from_acct.isin(nodes) & e.to_acct.isin(nodes)]
    return (e.groupby(["from_acct", "to_acct"])
             .agg(amt=("amt_vnd", "sum"), n=("amt_vnd", "size"), lab=("is_laundering", "max"))
             .reset_index())


@st.cache_data(show_spinner=False, max_entries=256)
def network_fig(acc_id: str, hops: int):
    """3 lớp vẽ (cạnh theo 3 độ dày, đầu mũi tên, nút) thay cho một annotation mỗi cạnh."""
    edges = ego_edges(acc_id, hops)
    if edges.empty:
        return None
    G = nx.DiGraph()
    G.add_node(acc_id)
    G.add_edges_from(edges[["from_acct", "to_acct"]].itertuples(index=False, name=None))
    pos = nx.spring_layout(G, seed=1, k=1.4 / np.sqrt(max(len(G), 1)))
    p0 = np.array([pos[a] for a in edges.from_acct])
    p1 = np.array([pos[a] for a in edges.to_acct])
    tier = np.digitize(np.log10(edges.amt.clip(lower=1)), [8, 9])  # <100 tr · <1 tỷ · ≥1 tỷ
    fig = go.Figure()
    for t, width in enumerate((0.8, 1.6, 3.0)):
        m = tier == t
        if not m.any():
            continue
        xs = np.column_stack([p0[m, 0], p1[m, 0], np.full(m.sum(), np.nan)]).ravel()
        ys = np.column_stack([p0[m, 1], p1[m, 1], np.full(m.sum(), np.nan)]).ravel()
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(width=width, color="#b4bcb8"),
                                 hoverinfo="skip"))
    d = p1 - p0
    head = p0 + d * 0.86  # đầu mũi tên đặt trước nút đích
    fig.add_trace(go.Scatter(
        x=head[:, 0], y=head[:, 1], mode="markers", hoverinfo="text",
        marker=dict(symbol="triangle-up", size=9, color="#8d9692",
                    angle=np.degrees(np.arctan2(d[:, 0], d[:, 1]))),
        hovertext=[f"{a} → {b}<br>{vnd(v)} · {int(n)} GD"
                   for a, b, v, n in edges[["from_acct", "to_acct", "amt", "n"]].itertuples(index=False)]))
    nodes = list(G.nodes())
    info = acc.reindex(nodes)
    simo_hit = info.simo_hit.fillna(False).astype(bool)
    hot = info.priority.fillna(0) >= core.ALERT_THRESHOLD
    color = [INK if n == acc_id else DANGER if simo_hit[n] else ACCENT if hot[n] else "#b9c1bd"
             for n in nodes]
    size = [22 if n == acc_id else 12 for n in nodes]
    fig.add_trace(go.Scatter(
        x=[pos[n][0] for n in nodes], y=[pos[n][1] for n in nodes], mode="markers+text",
        marker=dict(size=size, color=color, line=dict(width=1.5, color="#fff")),
        text=[n if n == acc_id or c != "#b9c1bd" else "" for n, c in zip(nodes, color)],
        textposition="top center", textfont=dict(size=11, color=MUTED),
        hoverinfo="text",
        hovertext=[f"{n}<br>Ưu tiên {info.loc[n, 'priority']:.0f}" if pd.notna(info.loc[n, "priority"]) else n
                   for n in nodes]))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, scaleanchor="x")  # cùng tỷ lệ để góc mũi tên đúng
    return style_fig(fig, 460)


def timeline_fig(acc_id: str, rel: pd.DataFrame):
    out = rel.from_acct == acc_id
    fig = go.Figure()
    fig.add_hrect(y0=core.STRUCT_LOW_VND, y1=core.LARGE_VALUE_VND, fillcolor=ACCENT, opacity=0.08, line_width=0)
    fig.add_hline(y=core.LARGE_VALUE_VND, line=dict(color=ACCENT, width=1.5, dash="dash"),
                  annotation_text="Ngưỡng 400 triệu", annotation_position="top left",
                  annotation_font=dict(color=ACCENT, size=12))
    for mask, name, col in ((out, "Chuyển đi", INK), (~out, "Nhận về", "#9aa39f")):
        d = rel[mask]
        fig.add_trace(go.Scatter(
            x=d.ts, y=d.amt_vnd.clip(lower=1e4), mode="markers", name=name,
            marker=dict(size=8, color=col, symbol="circle" if name == "Chuyển đi" else "circle-open",
                        line=dict(width=1.5, color=col)),
            hovertext=[f"{name} · {vnd(a)}<br>{t:%d/%m %H:%M} · {f}" for a, t, f in zip(d.amt_vnd, d.ts, d.fmt_vi)],
            hoverinfo="text"))
    fig.update_yaxes(type="log", gridcolor=GRID, zeroline=False, title=None,
                     tickvals=[1e6, 1e7, 1e8, 4e8, 1e9, 1e10, 1e11],
                     ticktext=["1 tr", "10 tr", "100 tr", "400 tr", "1 tỷ", "10 tỷ", "100 tỷ"])
    fig.update_xaxes(showgrid=False, tickformat="%d/%m")
    fig = style_fig(fig, 300)
    fig.update_layout(showlegend=True, legend=dict(orientation="h", y=1.12, x=1, xanchor="right"))
    return fig


def str_draft(acc_id: str, row, rel: pd.DataFrame, note: str) -> str:
    lines = [
        f"# Dự thảo hồ sơ giao dịch đáng ngờ — tài khoản {acc_id}",
        "",
        f"Lập ngày {datetime.now():%d/%m/%Y %H:%M} bởi {st.session_state.analyst}. "
        "Bản nháp nội bộ để chuyên viên hoàn thiện theo mẫu báo cáo chính thức của NHNN; không gửi trực tiếp.",
        "",
        "## Thông tin tài khoản",
        f"- Số tài khoản: {acc_id} · Ngân hàng: NH-{row.bank}",
        f"- Điểm ưu tiên: {row.priority:.0f}/100 (điểm mẫu hình {row.risk:.0f})",
        f"- Danh sách SIMO: {'có' if row.simo_hit else 'gần (≤ 2 bước)' if row.simo_near else 'không'}",
        f"- Tổng chuyển đi: {vnd(row.out_vnd)} ({int(row.out_n)} GD) · tổng nhận: {vnd(row.in_vnd)} ({int(row.in_n)} GD)",
        "",
        "## Dấu hiệu nghi ngờ",
        *[f"- {core.FLAG_LABELS[f]}" for f in row.signals],
        *([f"- Nằm trên vòng tròn chuyển tiền dài {int(row.cycle_len)} bước"] if pd.notna(row.cycle_len) else []),
        "",
        "## Giao dịch liên quan (tối đa 30, mới nhất trước)",
        "| Thời điểm | Từ | Đến | Số tiền | Hình thức |",
        "|---|---|---|---|---|",
        *[f"| {r.ts:%d/%m/%Y %H:%M} | {r.from_acct} | {r.to_acct} | {vnd(r.amt_vnd)} | {r.fmt_vi} |"
          for r in rel.head(30).itertuples()],
        "",
        "## Nhận định của chuyên viên",
        note or "(chưa nhập)",
    ]
    return "\n".join(lines)


@st.fragment
def network_panel(sel: str):
    """Fragment: đổi phạm vi 1/2 bước chỉ chạy lại khối này, không chạy lại cả trang."""
    h1, h2 = st.columns([3, 1])
    h1.markdown("### Mạng lưới dòng tiền")
    hops = h2.segmented_control("Phạm vi", [1, 2], default=1, format_func=lambda h: f"{h} bước",
                                label_visibility="collapsed", key=f"hops_{sel}") or 1
    fig = network_fig(sel, hops)
    if fig is None:
        st.markdown('<p class="note">Tài khoản chỉ có giao dịch tự chuyển, không có đối tác để vẽ.</p>',
                    unsafe_allow_html=True)
        return
    st.plotly_chart(fig, config={"displayModeBar": False}, key=f"net_{sel}_{hops}")
    st.markdown(f'<p class="note">Đen: tài khoản đang xem · xanh: cũng vượt ngưỡng {core.ALERT_THRESHOLD} · '
                'đỏ: có trong danh sách SIMO. Độ dày cạnh theo tổng tiền (dưới 100 triệu, dưới 1 tỷ, từ 1 tỷ).</p>',
                unsafe_allow_html=True)


def page_case():
    options = list(pool.index[:CASE_OPTIONS])
    current = st.session_state.get("account") or options[0]
    if current not in options:
        options.insert(0, current)
    sel = st.selectbox("Tài khoản", options, index=options.index(current), placeholder="Nhập số tài khoản")
    st.session_state.account = sel
    row = acc.loc[sel]

    st.title(f"Hồ sơ tài khoản {sel}")
    st.markdown(pills(row), unsafe_allow_html=True)
    rel = tx.iloc[rows_of([sel])]  # tx đã sắp mới nhất trước

    kpi_strip([
        ("Điểm ưu tiên", f"{row.priority:.0f}", "/100", True),
        ("Tiền chuyển đi", vnd(row.out_vnd), f"{num(row.out_n)} GD", False),
        ("Tiền nhận về", vnd(row.in_vnd), f"{num(row.in_n)} GD", False),
        ("Đối tác nhiều nhất trong 72h", f"{int(max(row.fan_out_max, row.fan_in_max))}", "tài khoản", False),
    ])

    left, right = st.columns([1.35, 1], gap="large")
    with left:
        network_panel(sel)
    with right:
        st.markdown("### Số tiền theo thời gian")
        st.plotly_chart(timeline_fig(sel, rel), config={"displayModeBar": False})
        st.markdown('<p class="note">Dải xanh nhạt là vùng 340–400 triệu, nơi các giao dịch chia nhỏ để né '
                    'ngưỡng báo cáo giá trị lớn thường rơi vào.</p>', unsafe_allow_html=True)

    st.markdown("### Giao dịch liên quan")
    show = pd.DataFrame({
        "Thời điểm": rel.ts, "Chiều": np.where(rel.from_acct == sel, "Chuyển đi", "Nhận về"),
        "Đối tác": np.where(rel.from_acct == sel, rel.to_acct, rel.from_acct),
        "NH đối tác": "NH-" + np.where(rel.from_acct == sel, rel.to_bank, rel.from_bank),
        "Số tiền (VND)": rel.amt_vnd.round(0), "Nguyên tệ": rel.amt_paid.round(2),
        "Tiền tệ": rel.cur_paid.astype(str), "Hình thức": rel.fmt_vi,
    })
    st.dataframe(show, hide_index=True, width="stretch", height=300, column_config={
        "Thời điểm": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
        "Số tiền (VND)": st.column_config.NumberColumn(format="localized"),
        "Nguyên tệ": st.column_config.NumberColumn(format="localized"),
    })

    st.markdown("### Quyết định của chuyên viên")
    past = decisions[decisions.account == sel]
    if len(past):
        last = past.iloc[-1]
        st.markdown(f'<p class="note">Lần gần nhất: <b>{escape(str(last.ket_luan))}</b> — '
                    f'{escape(str(last.nguoi_quyet_dinh))}, {escape(str(last.thoi_diem))}</p>', unsafe_allow_html=True)
    with st.form("decision"):
        ket_luan = st.radio("Kết luận", [
            "Không đáng ngờ, đóng cảnh báo", "Tiếp tục theo dõi",
            "Lập báo cáo giao dịch đáng ngờ", "Đề xuất cập nhật lên SIMO",
        ], horizontal=True)
        ghi_chu = st.text_area("Lý do", placeholder="Ví dụ: tiền vào từ 6 tài khoản trong 2 ngày rồi chuyển hết sang 1 tài khoản tại NH khác")
        ok = st.form_submit_button("Lưu quyết định", type="primary")
    if ok:
        if not ghi_chu.strip():
            st.error("Cần ghi lý do trước khi lưu — nhật ký phải giải thích được mỗi quyết định.")
        else:
            save_decision(sel, ket_luan, ghi_chu.strip(), st.session_state.analyst)
            st.success(f"Đã lưu quyết định cho {sel}.")
    st.download_button("Tải dự thảo hồ sơ (.md)", str_draft(sel, row, rel, ghi_chu if ok else ""),
                       file_name=f"du_thao_STR_{sel}.md", mime="text/markdown")


# ---------- Trang: Mẫu hình & kiểm chứng ----------
@st.cache_resource(show_spinner="Đang tính chỉ số kiểm chứng…")
def validation(k: int = 1000):
    """Chỉ số cố định theo dữ liệu đã xử lý, tính một lần cho cả phiên."""
    from sklearn.metrics import average_precision_score, roc_auc_score

    y = acc.is_laundering.astype(int)
    alert = acc.risk >= core.ALERT_THRESHOLD
    kpis = [
        ("PR-AUC điểm mẫu hình", f"{average_precision_score(y, acc.risk):.3f}",
         f"tỷ lệ nền {y.mean():.4f}", True),
        ("ROC-AUC", f"{roc_auc_score(y, acc.risk):.3f}", "", False),
        (f"Độ chính xác trong {num(k)} điểm cao nhất", f"{acc.nlargest(k, 'risk').is_laundering.mean():.1%}", "", False),
        (f"Độ phủ ở ngưỡng {core.ALERT_THRESHOLD}", f"{acc[alert].is_laundering.sum() / y.sum():.1%}",
         f"{num(alert.sum())} cảnh báo", False),
    ]
    rows = []
    for f, label in core.FLAG_LABELS.items():
        m = acc[f"s_{f}"] >= 1
        rows.append({"Dấu hiệu": label, "Tài khoản bị gắn": int(m.sum()),
                     "Trong đó rửa tiền": int((m & acc.is_laundering).sum()),
                     "Độ chính xác": (m & acc.is_laundering).sum() / max(m.sum(), 1)})
    p = acc[acc.pattern.notna()]
    rec = (p.assign(hit=p.risk >= core.ALERT_THRESHOLD).groupby("pattern")
            .agg(n=("hit", "size"), hit=("hit", "mean")).sort_values("hit"))
    return kpis, pd.DataFrame(rows), rec


def page_patterns():
    st.title("Mẫu hình và kiểm chứng")
    st.markdown('<p class="lead">Điểm mẫu hình được đối chiếu với nhãn rửa tiền có sẵn của bộ dữ liệu IBM '
                '(tài khoản có ít nhất một giao dịch rửa tiền). Ngân hàng thật không có nhãn này; '
                'trang này chỉ để đánh giá bộ quy tắc trước khi dùng.</p>', unsafe_allow_html=True)
    kpis, signals_tbl, rec = validation()
    kpi_strip(kpis)

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("### Từng dấu hiệu bắt được bao nhiêu")
        st.dataframe(signals_tbl, hide_index=True, width="stretch", column_config={
            "Tài khoản bị gắn": st.column_config.NumberColumn(format="localized"),
            "Trong đó rửa tiền": st.column_config.NumberColumn(format="localized"),
            "Độ chính xác": st.column_config.NumberColumn(format="percent"),
        })
    with c2:
        st.markdown(f"### Độ phủ theo loại mẫu hình (ngưỡng {core.ALERT_THRESHOLD})")
        fig = go.Figure(go.Bar(x=rec.hit, y=rec.index, orientation="h", marker_color=ACCENT,
                               text=[f"{h:.0%} của {n}" for h, n in zip(rec.hit, rec.n)],
                               textposition="outside", cliponaxis=False))
        fig.update_xaxes(range=[0, 1.15], tickformat=".0%", gridcolor=GRID, zeroline=False)
        st.plotly_chart(style_fig(fig, 340), config={"displayModeBar": False})
    st.markdown('<p class="note">Ngưỡng, trọng số và cửa sổ thời gian được khoá trước khi đánh giá '
                '(aml_core.py). Chi tiết và so sánh với điểm gốc của demo1.py trong '
                'notebooks/01_aml_graph_analysis.ipynb.</p>', unsafe_allow_html=True)


# ---------- Trang: Nhật ký ----------
def page_log():
    st.title("Nhật ký quyết định")
    if decisions.empty:
        st.markdown('<p class="lead">Chưa có quyết định nào. Mở một tài khoản từ hàng đợi, ghi kết luận và lý do; '
                    'mỗi quyết định được lưu kèm người và thời điểm.</p>', unsafe_allow_html=True)
        return
    counts = decisions.ket_luan.value_counts()
    st.markdown(f'<p class="lead"><b>{num(len(decisions))}</b> quyết định cho '
                f'<b>{num(decisions.account.nunique())}</b> tài khoản; '
                f'{num(counts.get("Lập báo cáo giao dịch đáng ngờ", 0))} chuyển lập báo cáo, '
                f'{num(counts.get("Đề xuất cập nhật lên SIMO", 0))} đề xuất cập nhật SIMO.</p>',
                unsafe_allow_html=True)
    log = decisions.iloc[::-1].rename(columns={
        "account": "Tài khoản", "ket_luan": "Kết luận", "ghi_chu": "Lý do",
        "thoi_diem": "Thời điểm", "nguoi_quyet_dinh": "Chuyên viên"})
    st.dataframe(log, hide_index=True, width="stretch")
    simo = decisions[decisions.ket_luan == "Đề xuất cập nhật lên SIMO"].drop_duplicates("account", keep="last")
    c1, c2 = st.columns(2)
    c1.download_button("Tải toàn bộ nhật ký (.csv)", decisions.to_csv(index=False).encode("utf-8-sig"),
                       file_name="nhat_ky_quyet_dinh.csv", mime="text/csv")
    c2.download_button(f"Tải danh sách đề xuất SIMO ({len(simo)})",
                       simo.to_csv(index=False).encode("utf-8-sig"),
                       file_name="de_xuat_SIMO.csv", mime="text/csv", disabled=simo.empty)


PAGES = {
    "queue": st.Page(page_queue, title="Hàng đợi cảnh báo", url_path="hang-doi", default=True),
    "case": st.Page(page_case, title="Hồ sơ tài khoản", url_path="ho-so"),
    "patterns": st.Page(page_patterns, title="Mẫu hình và kiểm chứng", url_path="mau-hinh"),
    "log": st.Page(page_log, title="Nhật ký quyết định", url_path="nhat-ky"),
}
st.navigation(list(PAGES.values())).run()
