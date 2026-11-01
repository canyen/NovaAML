"""Chạy một lần trên máy mới: tải IBM AML (HI-Small) từ Kaggle và tạo data/processed/.

    python prepare_data.py            # HI-Small (mặc định)
    python prepare_data.py LI-Small   # tập tỷ lệ rửa tiền thấp
"""
import json
import sys
import time

import aml_core

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # console Windows mặc định cp1252
    variant = sys.argv[1] if len(sys.argv) > 1 else aml_core.VARIANT
    t = time.time()
    meta = aml_core.prepare(variant)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"Xong sau {time.time() - t:.0f} giây. Chạy app: streamlit run app.py")
