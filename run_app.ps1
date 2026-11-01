# Mở NovaAML: tạo .venv nếu chưa có, cài thư viện nếu thiếu, chuẩn bị dữ liệu nếu thiếu, rồi chạy app.
# Cách dùng (PowerShell, tại thư mục dự án):  powershell -ExecutionPolicy Bypass -File .\run_app.ps1
# Không dùng "Stop": PowerShell 5.1 coi stderr của python là lỗi và dừng script. Kiểm tra $LASTEXITCODE thay vào đó.
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$py = ".\.venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "Tạo môi trường .venv..."
    python -m venv .venv
}

& $py -c "import importlib.util, sys; sys.exit(importlib.util.find_spec('streamlit') is None)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Cài thư viện (lần đầu mất vài phút)..."
    & $py -m pip install --upgrade pip
    & $py -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { Write-Host "Cài thư viện thất bại, xem lỗi phía trên." -ForegroundColor Red; exit 1 }
}

if (-not (Test-Path ".\data\processed\accounts.parquet")) {
    Write-Host "Tải dữ liệu từ Kaggle và xử lý..."
    & $py prepare_data.py
    if ($LASTEXITCODE -ne 0) { Write-Host "Chuẩn bị dữ liệu thất bại, xem lỗi phía trên." -ForegroundColor Red; exit 1 }
}

Write-Host "Mở app tại http://localhost:8501  (Ctrl+C để dừng)"
Start-Process "http://localhost:8501"
& $py -m streamlit run app.py
