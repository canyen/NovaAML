# NovaAML — phân tích mạng lưới rửa tiền (demo)

Lớp phân tích đồ thị đặt trên hệ thống giám sát giao dịch lõi (TMS) và SIMO của NHNN mà ngân hàng đã có.
TMS bắt từng giao dịch vượt quy tắc; NovaAML nhìn **mạng lưới**: vòng tròn khép kín, gom–rải tiền,
chuyển tiếp nhanh, chia nhỏ sát ngưỡng 400 triệu, và khoảng cách tới tài khoản đã có trên SIMO.

Xem demo trực tuyến tại: https://novaaml-srdje7n8zuvnktzu7hnzhn.streamlit.app/

Dữ liệu: [IBM Transactions for Anti Money Laundering](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml)
(bản `HI-Small`: 5.078.345 giao dịch, 515.080 tài khoản, 01–18/09/2022, dữ liệu tổng hợp có nhãn).
Tải tự động từ Kaggle bằng `kagglehub`, không cần API key. Kết nối TMS và SIMO trong demo là **mô phỏng**.

---

## 1. Khởi động

### Cách nhanh (Windows)

Mở terminal PowerShell tại thư mục dự án và chạy:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_app.ps1
```

Script tự làm theo thứ tự: tạo `.venv` nếu chưa có → cài thư viện nếu thiếu → tải và xử lý dữ liệu nếu thiếu →
mở trình duyệt tại `http://localhost:8501`. Lần đầu mất 5–10 phút; các lần sau mở ngay.
Dừng app: bấm `Ctrl + C` trong terminal.

### Cách thủ công (mọi hệ điều hành)

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python prepare_data.py            # tải ~475 MB từ Kaggle + xử lý, 3–5 phút, cần ~4 GB RAM
streamlit run app.py
```

### Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `streamlit is not recognized` | Thư viện chưa cài vào `.venv`. Chạy `.\.venv\Scripts\python -m pip install -r requirements.txt` |
| `running scripts is disabled` khi activate | Dùng lệnh `run_app.ps1` ở trên (đã có `-ExecutionPolicy Bypass`) |
| Trình duyệt mở nhưng trang trắng | Đợi vài giây cho app nạp dữ liệu (~7 giây lần đầu) rồi bấm F5 |
| Cổng 8501 bận | `streamlit run app.py --server.port 8502` |
| App báo "Chưa có dữ liệu" | Bấm nút **Tải và xử lý dữ liệu**, hoặc chạy `python prepare_data.py` |

### Đưa lên mạng (Streamlit Community Cloud)

GitHub chỉ chứa code; app chạy trên [Streamlit Community Cloud](https://share.streamlit.io) (miễn phí), lấy code từ repo.

1. Đẩy repo lên GitHub (repo private cũng được).
2. Vào share.streamlit.io → đăng nhập bằng GitHub → **Create app** → chọn repo, nhánh `main`, file chính `app.py`.
3. Bấm **Deploy**. Lần đầu mất vài phút để cài thư viện.

Repo đã kèm `data/processed/` (25 MB) vì máy chủ miễn phí không đủ RAM để tự xử lý 5 triệu giao dịch.
Trên Cloud, nhật ký quyết định **dùng chung cho mọi người xem** và **mất khi app khởi động lại** —
chỉ dùng để demo, không dùng làm hồ sơ thật. Muốn giới hạn người xem: trong cài đặt app trên Cloud,
mục *Sharing*, chỉ cho phép email được mời.

---

## 2. Dùng app

Thanh bên trái có tên ngân hàng đang xem (`NH-070`, ngân hàng có nhiều giao dịch nhất trong dữ liệu),
khoảng thời gian dữ liệu, trạng thái TMS/SIMO (mô phỏng) và ô **Chuyên viên**. Tên trong ô này được ghi vào
mỗi quyết định, nên hãy nhập tên mình trước khi làm việc.

Luồng làm việc điển hình: **Hàng đợi → chọn tài khoản → Hồ sơ → ghi quyết định → Nhật ký**.

### 2.1 Hàng đợi cảnh báo

Trả lời câu hỏi: *hôm nay xem tài khoản nào trước?*

| Điều khiển | Tác dụng |
|---|---|
| **Điểm ưu tiên tối thiểu** (mặc định 50) | Chỉ hiện tài khoản có điểm ưu tiên từ mức này trở lên |
| **Mẫu hình** | Chỉ hiện tài khoản có **đủ tất cả** dấu hiệu được chọn |
| **Chỉ liên quan SIMO** | Chỉ hiện tài khoản trùng hoặc gần danh sách SIMO |
| **Ẩn đã xử lý** | Bỏ các tài khoản đã có quyết định khỏi danh sách |

**Bấm vào một dòng** trong bảng để mở hồ sơ tài khoản đó. Bảng hiện tối đa 1.000 dòng; nếu nhiều hơn,
chú thích dưới bảng sẽ nói rõ — tăng ngưỡng để thu hẹp.

### 2.2 Hồ sơ tài khoản

Trả lời câu hỏi: *tài khoản này có thật sự đáng ngờ không, và vì sao?*

1. **Ô chọn tài khoản** ở đầu trang: 3.000 tài khoản ưu tiên cao nhất (gõ để tìm).
2. **Các nhãn màu** dưới tiêu đề: dấu hiệu đã khớp. Nhãn đỏ = liên quan SIMO.
3. **Mạng lưới dòng tiền**: chọn **1 bước** (đối tác trực tiếp) hoặc **2 bước** (đối tác của đối tác).
   Rê chuột lên đầu mũi tên để xem tổng tiền và số giao dịch giữa hai tài khoản; rê lên nút để xem điểm ưu tiên.
4. **Số tiền theo thời gian**: mỗi chấm là một giao dịch.
5. **Giao dịch liên quan**: bảng đầy đủ, mới nhất trước. Bấm tiêu đề cột để sắp xếp.
6. **Quyết định của chuyên viên**: chọn kết luận, **bắt buộc ghi lý do**, bấm **Lưu quyết định**.
7. **Tải dự thảo hồ sơ (.md)**: bản nháp nội bộ gồm thông tin tài khoản, dấu hiệu, 30 giao dịch gần nhất
   và nhận định — để hoàn thiện theo mẫu báo cáo chính thức, không gửi trực tiếp.

| Kết luận | Dùng khi |
|---|---|
| Không đáng ngờ, đóng cảnh báo | Có giải thích hợp lý (lương, thanh toán nhà cung cấp quen…) |
| Tiếp tục theo dõi | Chưa đủ căn cứ, cần xem thêm dữ liệu |
| Lập báo cáo giao dịch đáng ngờ | Đủ căn cứ để chuyển bộ phận lập báo cáo |
| Đề xuất cập nhật lên SIMO | Tài khoản nên được báo lên SIMO (vào danh sách tải ở trang Nhật ký) |

### 2.3 Mẫu hình và kiểm chứng

Đối chiếu điểm của app với nhãn rửa tiền có sẵn trong bộ dữ liệu IBM. **Ngân hàng thật không có nhãn này**;
trang này để đánh giá bộ quy tắc có đáng tin không trước khi dùng. Cách đọc ở mục 3.5.

### 2.4 Nhật ký quyết định

Mọi quyết định kèm người, thời điểm và lý do, mới nhất ở trên. Hai nút tải:
**toàn bộ nhật ký (.csv)** và **danh sách đề xuất SIMO (.csv)** (mỗi tài khoản lấy quyết định gần nhất).
File tải về từ hai nút này mở thẳng bằng Excel vẫn hiện đúng tiếng Việt. Bản gốc lưu ở `data/decisions.csv`
(UTF-8 không BOM — mở bằng Excel qua *Data → From Text/CSV*).

---

## 3. Cách đọc số

### 3.1 Tiền

- Mọi số tiền đã quy đổi sang **VND**: nguyên tệ → USD theo tỷ giá ngầm định trong chính dữ liệu →
  VND theo **26.000 VND/USD** (giả định, đổi ở `USD_VND` trong `aml_core.py`).
- Cách viết: `1,25 tỷ` = 1.250.000.000 đ · `350 triệu` = 350.000.000 đ · `12.500 đ`.
- Cột **Tiền ra (triệu)** / **Tiền vào (triệu)** ở hàng đợi tính bằng triệu đồng: `271.709` = khoảng 271,7 tỷ.
- Cột **Nguyên tệ** trong bảng giao dịch là số tiền gốc theo cột **Tiền tệ** bên cạnh.
- Tổng tiền **không tính giao dịch tự chuyển** (cùng một tài khoản gửi và nhận).

### 3.2 Sáu dấu hiệu

Mỗi dấu hiệu cho một **mức độ từ 0 đến 1**, nhân với trọng số rồi cộng lại thành điểm mẫu hình.

| Dấu hiệu | Định nghĩa | Đạt mức 1 khi | Trọng số |
|---|---|---|---|
| Rải tiền (fan-out) | Số người nhận khác nhau trong một khối 72 giờ | ≥ 5 người nhận | 20 |
| Gom tiền (fan-in) | Số người gửi khác nhau trong một khối 72 giờ | ≥ 5 người gửi | 20 |
| Vòng tròn khép kín | Tiền đi qua 2–6 tài khoản rồi quay về chính nó trong 7 ngày | Có ít nhất một vòng | 25 |
| Chuyển tiếp nhanh | Trong 48 giờ, tiền ra bằng 90–110% tiền vào, tiền vào ≥ 100 triệu | Có ít nhất một lần | 15 |
| Chia nhỏ sát ngưỡng 400 triệu | Số giao dịch 340–400 triệu trong một khối 72 giờ | ≥ 3 giao dịch | 15 |
| Đổi tiền tệ / tài sản mã hoá | Tiền tệ gửi khác tiền tệ nhận, hoặc có Bitcoin | Có ít nhất một lần | 5 |

Mức độ tăng dần: 1 đối tác = 0; 3 đối tác = 0,5; từ 5 trở lên = 1. Chia nhỏ: 1 giao dịch = 0,33; 2 = 0,67; 3 = 1.

> **Lưu ý khi đọc:** cột **Dấu hiệu** và các nhãn màu chỉ liệt kê dấu hiệu **đạt đủ mức 1**.
> Dấu hiệu đạt một phần vẫn cộng điểm nhưng không hiện tên — vì vậy điểm có thể cao hơn tổng trọng số của các nhãn bạn thấy.

### 3.3 Điểm mẫu hình và điểm ưu tiên

```
Điểm mẫu hình (0–100) = Σ trọng số × mức độ
Điểm ưu tiên          = điểm mẫu hình + 25 nếu trùng SIMO, hoặc + 10 nếu cách tài khoản SIMO ≤ 2 bước  (tối đa 100)
```

**Ví dụ thật từ dữ liệu:**

| | `811D80C30` | `8041A3440` |
|---|---|---|
| Rải tiền | 6 người nhận → 1 × 20 = 20 | 9 người nhận → 20 |
| Gom tiền | 13 người gửi → 20 | 8 người gửi → 20 |
| Vòng tròn | vòng 2 bước → 25 | không → 0 |
| Chuyển tiếp nhanh | không → 0 | có → 15 |
| Chia nhỏ | 2 GD sát ngưỡng → 0,67 × 15 = 10 | 1 GD → 0,33 × 15 = 5 |
| Đổi tiền tệ | có → 5 | có → 5 |
| **Điểm mẫu hình** | **80** | **65** |
| SIMO | gần (≤ 2 bước) → +10 | trùng → +25 |
| **Điểm ưu tiên** | **90** | **90** |

Hai tài khoản cùng ưu tiên 90 nhưng vì hai lý do khác nhau: tài khoản đầu do chính hành vi của nó,
tài khoản sau phần lớn nhờ đã có trên SIMO. Luôn xem **cả hai cột** Ưu tiên và Điểm mẫu hình.

**Mức tham khảo** trên dữ liệu này: 2.006 tài khoản có ưu tiên ≥ 50, 59 tài khoản ≥ 70, 2 tài khoản ≥ 90.
Điểm là **thứ tự để xem trước**, không phải xác suất rửa tiền: điểm 80 không có nghĩa là "80% khả năng".

### 3.4 Hàng đợi và hồ sơ

| Chỉ số | Nghĩa |
|---|---|
| **Cảnh báo mở** | Số tài khoản khớp bộ lọc và chưa có quyết định |
| **Liên quan SIMO** | Trong số đó, bao nhiêu trùng hoặc gần danh sách SIMO |
| **Đã có quyết định** | Số tài khoản khớp bộ lọc đã được chuyên viên kết luận |
| **GD ≥ 400 triệu (TMS đã báo cáo)** | Giao dịch giá trị lớn mà TMS lõi đã báo cáo — bối cảnh, không cộng điểm |
| Cột **SIMO** | `Trùng` = có trong danh sách SIMO · `Gần` = giao dịch với tài khoản SIMO hoặc với đối tác của nó · trống = không liên quan |
| **Đối tác nhiều nhất trong 72h** | Số người gửi hoặc nhận khác nhau lớn nhất trong một khối 72 giờ (lấy chiều lớn hơn) |

**Mạng lưới dòng tiền**

| Thấy gì | Nghĩa |
|---|---|
| Nút đen, to | Tài khoản đang xem |
| Nút xanh | Đối tác cũng vượt ngưỡng ưu tiên 50 — đáng mở tiếp |
| Nút đỏ | Đối tác có trong danh sách SIMO |
| Nút xám | Đối tác chưa có dấu hiệu |
| Tam giác trên cạnh | Chiều dòng tiền (tam giác chỉ về phía người nhận) |
| Cạnh mảnh / vừa / đậm | Tổng tiền giữa hai tài khoản: dưới 100 triệu / dưới 1 tỷ / từ 1 tỷ |

Mỗi bước chỉ giữ 25 đối tác có tổng tiền lớn nhất để hình còn đọc được. Mẫu hình cần tìm:
nhiều mũi tên **vào rồi một mũi tên ra** (gom), **một vào rồi nhiều ra** (rải),
các nút **nối thành vòng** quay về nút đen (vòng tròn), nhiều nút xanh/đỏ dính nhau (cụm đáng ngờ).

**Số tiền theo thời gian**

- Trục dọc theo **thang log**: mỗi vạch lớn gấp 10 lần vạch dưới (1 tr, 10 tr, 100 tr, 1 tỷ…).
- **Chấm đặc** = chuyển đi · **chấm rỗng** = nhận về.
- **Đường gạch** = ngưỡng 400 triệu; **dải xanh nhạt** = vùng 340–400 triệu.
  Nhiều chấm đặc dồn vào dải này trong vài ngày là dấu hiệu chia nhỏ để né báo cáo.
- Chấm rỗng rồi chấm đặc cùng độ cao, cách nhau vài giờ = tiền vào rồi đi ngay (chuyển tiếp nhanh).

### 3.5 Trang kiểm chứng

Một tài khoản được coi là "rửa tiền" nếu tham gia ít nhất một giao dịch có nhãn rửa tiền (gửi hoặc nhận).
Trong dữ liệu này, 6.357 trên 515.080 tài khoản (**1,23%** — gọi là *tỷ lệ nền*).

| Chỉ số | Giá trị | Đọc thế nào |
|---|---|---|
| **PR-AUC** | 0,038 | Chất lượng xếp hạng khi nhãn rất hiếm. So với tỷ lệ nền 0,012: gấp ~3 lần chọn ngẫu nhiên. Điểm gốc của `demo1.py`: 0,027 |
| **ROC-AUC** | 0,732 | Xác suất một tài khoản rửa tiền được xếp trên một tài khoản sạch chọn ngẫu nhiên. 0,5 = đoán mò, 1 = hoàn hảo |
| **Độ chính xác trong 1.000 điểm cao nhất** | 13,5% | Xem 1.000 tài khoản đầu hàng đợi thì 135 tài khoản có liên quan — gấp ~11 lần tỷ lệ nền |
| **Độ phủ ở ngưỡng 50** | 1,8% | Trong mọi tài khoản rửa tiền, chỉ 1,8% có điểm mẫu hình ≥ 50 |

Bảng **Từng dấu hiệu bắt được bao nhiêu**: *Độ chính xác* = trong các tài khoản bị gắn dấu hiệu đó,
bao nhiêu phần trăm thật sự liên quan rửa tiền. Vòng tròn chính xác nhất (~9,8%); đổi tiền tệ phủ rộng nhưng nhiễu.

Biểu đồ **Độ phủ theo loại mẫu hình**: với mỗi kiểu vụ rửa tiền trong dữ liệu (FAN-OUT, CYCLE, SCATTER-GATHER…),
bao nhiêu phần trăm tài khoản tham gia có điểm ≥ 50.

**Kết luận đúng mực:** bộ quy tắc giúp **sắp xếp thứ tự xem** tốt hơn nhiều so với ngẫu nhiên và so với bản gốc,
nhưng **bỏ sót phần lớn** tài khoản — đặc biệt các tài khoản chỉ nhận một khoản trong một vụ rải tiền,
vì khi đứng riêng chúng không có dấu hiệu gì. Không dùng điểm này một mình để kết luận một tài khoản là sạch.
Chi tiết trong notebook.

---

## 4. Cấu trúc dự án

| File | Vai trò |
|---|---|
| `run_app.ps1` | Mở app một lệnh trên Windows |
| `app.py` | Ứng dụng Streamlit |
| `aml_core.py` | Tải Kaggle, quy đổi VND, các dấu hiệu, điểm, lớp SIMO mô phỏng. **Ngưỡng và trọng số ở đầu file** |
| `prepare_data.py` | Chạy một lần, ghi `data/processed/` (`python prepare_data.py LI-Small` cho tập tỷ lệ thấp) |
| `notebooks/01_aml_graph_analysis.ipynb` | Phân tích đầy đủ, đã chạy sẵn kèm kết quả |
| `output/` | `canh_bao_uu_tien.csv`, `danh_gia.json`, `figures/` |
| `demo1.py` | Bản demo gốc (dữ liệu sinh ngẫu nhiên), giữ để đối chiếu |
| `log/plans/` | Kế hoạch phân tích đã khoá trước khi đánh giá |

Xuất notebook sang HTML: `jupyter nbconvert --to html notebooks/01_aml_graph_analysis.ipynb --output-dir output`

---

## 5. Giới hạn cần nói rõ khi demo

- Dữ liệu IBM là **tổng hợp** và không mô phỏng ngưỡng 400 triệu của Việt Nam, nên dấu hiệu chia nhỏ ít tác dụng ở đây.
- `HI-Small` có tỷ lệ rửa tiền cao hơn thực tế; dùng `LI-Small` để có bối cảnh sát hơn.
- Danh sách SIMO là **mô phỏng**: 10% tài khoản rửa tiền + 0,05% tài khoản sạch được chọn ngẫu nhiên (seed cố định).
- Mã ngân hàng hiển thị dạng `NH-xxx`, không gắn với ngân hàng thật.
- Ngưỡng 400 triệu (giao dịch giá trị lớn, QĐ 11/2023/QĐ-TTg) và các tham chiếu pháp lý khác cần pháp chế đối chiếu văn bản hiện hành.
- Đổi ngưỡng hoặc trọng số trong `aml_core.py` sau khi đã xem kết quả là một phân tích mới — ghi lý do trước khi đổi.
