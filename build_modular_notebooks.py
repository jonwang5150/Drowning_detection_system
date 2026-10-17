"""Split v14_linebot_message.ipynb into portable, function-oriented notebooks."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parent
SOURCE_NOTEBOOK = ROOT / "v14_linebot_message.ipynb"


def lines(text: str) -> list[str]:
    """Return notebook-compatible source lines."""
    return text.strip("\n").splitlines(keepends=True) + ["\n"]


def markdown(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": lines(dedent(text))}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": lines(dedent(text)),
    }


def notebook(title: str, description: str, *code_cells: str) -> dict:
    cells = [markdown(f"# {title}\n\n{description}")]
    cells.extend(code(cell) for cell in code_cells)
    return {
        "cells": cells,
        "metadata": {
            "accelerator": "GPU",
            "colab": {"provenance": []},
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def node_source(source: str, tree: ast.Module, name: str) -> str:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
            start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
            end = node.end_lineno
            return "\n".join(source.splitlines()[start:end])
    raise KeyError(name)


def assignment_source(source: str, tree: ast.Module, name: str) -> str:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                return "\n".join(source.splitlines()[node.lineno - 1 : node.end_lineno])
    raise KeyError(name)


def write_notebook(filename: str, content: dict) -> None:
    (ROOT / filename).write_text(
        json.dumps(content, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


original = json.loads(SOURCE_NOTEBOOK.read_text(encoding="utf-8"))
source = "".join(original["cells"][2]["source"])
tree = ast.parse(source)


write_notebook(
    "00_environment.ipynb",
    notebook(
        "00｜執行環境",
        "安裝 Colab / Kaggle 執行此專案所需的套件。重複執行是安全的。",
        """
        %pip install -q "flask>=3,<4" "ultralytics>=8,<9" opencv-python-headless "line-bot-sdk>=3,<4"

        print("套件安裝完成。若剛升級核心套件後遇到匯入錯誤，請重新啟動工作階段再執行 main.ipynb。")
        """,
    ),
)


write_notebook(
    "01_model_setup.ipynb",
    notebook(
        "01｜模型與追蹤器設定",
        "尋找目前目錄的 `best.pt`；不存在時才從原專案網址下載，並依 GPU 可用性選擇裝置。",
        """
        from pathlib import Path
        import urllib.request
        import torch
        from ultralytics import YOLO

        PROJECT_DIR = Path.cwd()
        MODEL_URL = "https://github.com/jonwang5150/drowning_detection/raw/refs/heads/main/best.pt"
        MODEL_PATH = PROJECT_DIR / "best.pt"
        TRACKER_YAML = PROJECT_DIR / "custom_bytetrack.yaml"
        FIXED_TRACK_BUFFER = 150

        if not MODEL_PATH.exists():
            print(f"找不到 {MODEL_PATH.name}，正在下載模型……")
            urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        else:
            print(f"使用現有模型：{MODEL_PATH}")

        TRACKER_YAML.write_text(
            f'''tracker_type: bytetrack
        track_high_thresh: 0.25
        track_low_thresh: 0.1
        new_track_thresh: 0.25
        track_buffer: {FIXED_TRACK_BUFFER}
        match_thresh: 0.8
        fuse_score: True
        ''',
            encoding="utf-8",
        )

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = YOLO(str(MODEL_PATH))
        model.to(device)
        TRACKER_YAML = str(TRACKER_YAML)

        print(f"運算裝置：{device}")
        print(f"追蹤緩衝：{FIXED_TRACK_BUFFER}")
        print("模型類別：", model.names)
        """,
    ),
)


state_code = """
from pathlib import Path
import csv
import io
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template_string, request, send_file
from linebot import LineBotApi
from linebot.models import TextSendMessage

TARGET_CLASSES = ["Drowning", "Person out of water", "Swimming"]
DISPLAY_MAX_WIDTH = 720
WORK_DIR = Path.cwd()
UPLOAD_PATH = str(WORK_DIR / "uploaded_video.mp4")
LOG_PATH = str(WORK_DIR / "detection_log.csv")

app = Flask(__name__)

_black_frame = np.zeros((360, 640, 3), dtype=np.uint8)
cv2.putText(_black_frame, "No video loaded", (170, 180),
            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (150, 150, 150), 2)
_, _black_buffer = cv2.imencode(".jpg", _black_frame)
BLACK_FRAME_JPEG = _black_buffer.tobytes()
"""
state_code += "\n\n" + node_source(source, tree, "DetectionState")
state_code += "\n\nstate = DetectionState()"
for function_name in ("fmt_time", "extract_first_frame_jpeg", "resolve_source"):
    state_code += "\n\n" + node_source(source, tree, function_name)

write_notebook(
    "02_state_and_utils.ipynb",
    notebook(
        "02｜狀態與共用工具",
        "建立 Flask 應用程式、執行狀態、跨平台檔案路徑與影片工具函式。",
        state_code,
    ),
)


visualization_code = "\n\n".join(
    node_source(source, tree, name)
    for name in ("draw_dashboard", "draw_warning_banner")
)
write_notebook(
    "03_visualization.ipynb",
    notebook(
        "03｜偵測畫面視覺化",
        "繪製統計儀表板與溺水警示橫幅。",
        visualization_code,
    ),
)


write_notebook(
    "04_line_notification.ipynb",
    notebook(
        "04｜LINE 通知",
        "以背景執行緒送出 LINE 廣播訊息，避免阻塞影像處理。",
        node_source(source, tree, "send_line_text_async"),
    ),
)


write_notebook(
    "05_detection_engine.ipynb",
    notebook(
        "05｜溺水偵測引擎",
        "執行 YOLO 追蹤、時間窗判斷、影像標註、CSV 紀錄與警示通知。",
        node_source(source, tree, "processing_worker"),
    ),
)


route_names = (
    "index",
    "video_feed",
    "stats",
    "upload",
    "start",
    "stop",
    "pause",
    "resume",
    "download_log",
    "test_line",
)
routes_code = "\n\n".join(node_source(source, tree, name) for name in route_names)
write_notebook(
    "06_web_api.ipynb",
    notebook(
        "06｜Flask Web API",
        "提供首頁、影像串流、狀態、上傳、控制、紀錄下載與 LINE 測試端點。",
        routes_code,
    ),
)


write_notebook(
    "07_web_ui.ipynb",
    notebook(
        "07｜Web 操作介面",
        "定義影片預覽、偵測參數、處理控制與 LINE 通知設定頁面。",
        assignment_source(source, tree, "HTML_PAGE"),
        'print("Web 操作介面已載入。")',
    ),
)


write_notebook(
    "08_server.ipynb",
    notebook(
        "08｜啟動 Flask 服務",
        "在背景執行 Flask；Colab 會顯示代理視窗，Kaggle/Jupyter 會提供代理連結。",
        r'''
        import os
        import socket
        import sys
        import threading
        import time
        from IPython.display import HTML, display


        def _port_is_open(port):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                return sock.connect_ex(("127.0.0.1", port)) == 0


        def launch_server(port=5000):
            """Start Flask once and expose the appropriate notebook link."""
            global flask_thread

            existing = globals().get("flask_thread")
            if existing is not None and existing.is_alive() and _port_is_open(port):
                print(f"Flask 已在連接埠 {port} 執行。")
            elif _port_is_open(port):
                raise RuntimeError(
                    f"連接埠 {port} 已被其他程式占用；請重新啟動工作階段，或改用其他 port。"
                )
            else:
                def run_flask():
                    app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)

                flask_thread = threading.Thread(target=run_flask, daemon=True)
                flask_thread.start()
                for _ in range(50):
                    if _port_is_open(port):
                        break
                    time.sleep(0.1)
                else:
                    raise RuntimeError("Flask 服務未能在預期時間內啟動。")
                print(f"Flask 已啟動：http://127.0.0.1:{port}")

            if "google.colab" in sys.modules:
                from google.colab import output
                output.serve_kernel_port_as_window(port)
            elif os.environ.get("KAGGLE_KERNEL_RUN_TYPE"):
                display(HTML(
                    '<p><strong>Flask 已在 Kaggle 核心內啟動。</strong></p>'
                    '<p>Kaggle 原生編輯器目前不會直接公開任意核心連接埠。'
                    '若要使用 Web 介面，請從 Kaggle 的「Run → Kaggle Jupyter Server」'
                    '選擇「Open in Colab」；連上同一個 Kaggle 後端後，再執行本 cell。</p>'
                ))
            else:
                proxy_path = f"/proxy/{port}/"
                display(HTML(
                    f'<p><a href="{proxy_path}" target="_blank">'
                    f'開啟溺水偵測系統（port {port}）</a></p>'
                    '<p>若目前平台未提供 notebook port proxy，請使用平台提供的 '
                    'Web Preview / Port Preview 功能開啟相同連接埠。</p>'
                ))
        ''',
    ),
)


main_nb = notebook(
    "溺水偵測系統｜主程式",
    "在 Colab 或 Kaggle 選擇「全部執行」即可依序載入所有功能並啟動 Web 操作介面。"
    "請將本專案的 notebooks 與 `best.pt` 放在同一目錄；若缺少模型會自動下載。",
    """
    from pathlib import Path
    import os
    import shutil

    MODULE_FILES = [
        "00_environment.ipynb", "01_model_setup.ipynb", "02_state_and_utils.ipynb",
        "03_visualization.ipynb", "04_line_notification.ipynb",
        "05_detection_engine.ipynb", "06_web_api.ipynb", "07_web_ui.ipynb",
        "08_server.ipynb",
    ]


    def prepare_runtime_directory():
        # Locate sibling modules and copy Kaggle read-only inputs to /kaggle/working.
        current = Path.cwd()
        if all((current / name).exists() for name in MODULE_FILES):
            return current

        kaggle_input = Path("/kaggle/input")
        if kaggle_input.exists():
            for first_module in kaggle_input.rglob(MODULE_FILES[0]):
                source_dir = first_module.parent
                if all((source_dir / name).exists() for name in MODULE_FILES):
                    runtime_dir = Path("/kaggle/working/drowning_detection")
                    runtime_dir.mkdir(parents=True, exist_ok=True)
                    for name in MODULE_FILES:
                        shutil.copy2(source_dir / name, runtime_dir / name)
                    if (source_dir / "best.pt").exists():
                        shutil.copy2(source_dir / "best.pt", runtime_dir / "best.pt")
                    os.chdir(runtime_dir)
                    print(f"已將 Kaggle 輸入檔複製到：{runtime_dir}")
                    return runtime_dir

        raise FileNotFoundError(
            "找不到功能 notebooks。請將 main.ipynb、00～08 notebooks 與 best.pt "
            "放在同一目錄；Kaggle 可將整個資料夾加入為 Dataset。"
        )


    RUNTIME_DIR = prepare_runtime_directory()
    print(f"執行目錄：{RUNTIME_DIR}")
    """,
    """
    # 如套件已安裝，可註解下一行以縮短再次執行的時間。
    %run -i ./00_environment.ipynb
    """,
    """
    # -i 讓各功能 notebook 共用目前的互動命名空間。
    %run -i ./01_model_setup.ipynb
    %run -i ./02_state_and_utils.ipynb
    %run -i ./03_visualization.ipynb
    %run -i ./04_line_notification.ipynb
    %run -i ./05_detection_engine.ipynb
    %run -i ./07_web_ui.ipynb
    %run -i ./06_web_api.ipynb
    %run -i ./08_server.ipynb

    print("所有功能模組載入完成。")
    """,
    """
    # 可改用 launch_server(port=其他連接埠)
    launch_server(port=5000)
    """,
)
write_notebook("main.ipynb", main_nb)

# README 是人工維護的完整專案文件，不由此產生器覆寫。
print("已建立 main.ipynb 與 9 個功能 notebooks；README.md 保持不變。")
