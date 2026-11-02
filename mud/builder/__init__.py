"""區域編輯器：用瀏覽器編輯 builder_area/ 裡的區域檔。

用法：uv run python -m mud.builder [--port 1234] [--host 0.0.0.0]
後端在 server.py（標準庫的 http.server），網頁在 static/（純 HTML／CSS／JS）。
檢查一律用 area.check_files()，規則只有一份。
"""
