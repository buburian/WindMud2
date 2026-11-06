"""區域編輯器的網頁伺服器：給網頁檔案，讀、存、檢查一個資料夾裡的區域檔。

API（內容都是 JSON）：
- GET  /api/areas                 檔案清單
- POST /api/areas                 新增區域檔 {"file", "title", "area_number"}
- GET  /api/areas/<檔名>          {"data": 內容, "problems": [...], "elsewhere": {遊戲號碼: 房間名},
                                   "elsewhere_mobiles": {遊戲號碼: 生物名}, "elsewhere_objects": {遊戲號碼: 物品名}}
                                   （elsewhere 是別的檔裡的）
- PUT  /api/areas/<檔名>          存檔（有問題也照樣存），回傳 {"problems": [...]}
- POST /api/areas/<檔名>/check    只檢查不存，回傳 {"problems": [...]}
出錯時回傳 {"error": 訊息}。
"""
import json
import logging
import os
import re
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .. import area

log = logging.getLogger(__name__)

STATIC = (Path(__file__).parent / "static").resolve()
NAME = re.compile(r"[A-Za-z0-9_-]+\.json")      # 檔名只收這種，擋掉 ../ 這類路徑
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8"}
AREA_URL = re.compile(r"/api/areas/([^/]+)")
CHECK_URL = re.compile(r"/api/areas/([^/]+)/check")


def dump(data):
    """存檔的格式，跟 areas/test.json 一樣：縮排 2、中文照寫、結尾不換行。"""
    return json.dumps(data, indent=2, ensure_ascii=False)


def new_area(name, title, area_number):
    """新的區域檔：一間「新房間」，其他欄位用手冊的預設值。"""
    return {
        "schema_version": 1,
        "file": name,
        "area": {
            "header": {"levels": [1, 1], "author": "", "title": title, "area_number": area_number, "type": "world"},
            "recall": None, "no_teleport": None, "clan_recall": None, "gem": None,
        },
        "rooms": [{"vnum": 1, "name": "新房間", "description": "", "room_flags": 0, "sector": 0,
                   "exits": {}, "extra_descriptions": [], "script": None}],
        "mobiles": [],
        "objects": [],
        "resets": [],
    }


class Problem(Exception):
    """要回給網頁的錯誤：HTTP 狀態碼和訊息。"""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class Builder:
    """存區域檔的資料夾。"""

    def __init__(self, folder):
        self.folder = Path(folder)

    def path(self, name):
        if not NAME.fullmatch(name):
            raise Problem(HTTPStatus.BAD_REQUEST, f"檔名只能用英文字母、數字、_、-，結尾是 .json：{name!r}")
        return self.folder / name

    def others(self, name):
        return sorted(p for p in self.folder.glob("*.json") if p.name != name)

    def problems(self, name, data):
        """用 check_files 檢查還沒存的內容：寫進暫存資料夾的同名檔，對照這個資料夾裡其他檔名的檔。

        同名的舊檔不拿來對照，不然每間房都會被當成跟舊檔重複。
        腳本的 .lua 照樣在這個資料夾裡找（例如 builder_area/test/），不是暫存資料夾。
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / name
            path.write_text(dump(data), encoding="utf-8")
            return area.check_files([path], self.others(name), script_root=self.folder)[path]

    def listing(self):
        result = []
        for path in sorted(self.folder.glob("*.json")):
            item = {"file": path.name}
            try:
                if not NAME.fullmatch(path.name):
                    raise ValueError("檔名只能用英文字母、數字、_、-")
                data = json.loads(path.read_text(encoding="utf-8"))
                item.update(title=data["area"]["header"]["title"], area_number=data["area"]["header"]["area_number"],
                            rooms=len(data["rooms"]))
            except (OSError, ValueError, KeyError, TypeError) as e:
                item["error"] = f"讀不到：{e}"
            result.append(item)
        return result

    def elsewhere(self, name, kind="rooms", label="name"):
        """別的檔的房間（kind="mobiles"、"objects" 是生物、物品）：遊戲號碼 → 名字。

        顯示「通到 3201」是哪間房、重置放的是哪隻生物用，看不懂的部分略過。
        """
        names = {}
        for path in self.others(name):
            data = area.read_json(path, [])
            try:
                base = data["area"]["header"]["area_number"]
                items = list(data[kind])
            except (KeyError, TypeError):
                continue
            if not area.is_int(base):
                continue
            for r in items:
                if isinstance(r, dict) and area.is_int(r.get("vnum")) and isinstance(r.get(label), str):
                    names.setdefault(base + r["vnum"], r[label])
        return names

    def read(self, name):
        path = self.path(name)
        problems = []
        data = area.read_json(path, problems)
        if data is None:
            raise Problem(HTTPStatus.NOT_FOUND if not path.exists() else HTTPStatus.BAD_REQUEST, problems[0])
        return {"data": data, "problems": self.problems(name, data), "elsewhere": self.elsewhere(name),
                "elsewhere_mobiles": self.elsewhere(name, "mobiles", "short"),
                "elsewhere_objects": self.elsewhere(name, "objects", "short")}

    def save(self, name, data):
        path = self.path(name)
        tmp = path.with_name(f".{name}.tmp")    # 先寫暫存檔再換名，不會寫壞一半
        tmp.write_text(dump(data), encoding="utf-8")
        os.replace(tmp, path)
        problems = self.problems(name, data)
        log.info(f"儲存 {name}（{len(problems)} 個問題）")
        return {"problems": problems}

    def create(self, body):
        if not isinstance(body, dict):
            raise Problem(HTTPStatus.BAD_REQUEST, "要寫成 {…}")
        name = body.get("file", "")
        path = self.path(name if isinstance(name, str) else "")
        if path.exists():
            raise Problem(HTTPStatus.CONFLICT, f"{name} 已經有了")
        path.write_text(dump(new_area(name, body.get("title", ""), body.get("area_number"))), encoding="utf-8")
        log.info(f"新增 {name}")
        return {"file": name}


class Handler(BaseHTTPRequestHandler):
    """builder 掛在 self.server.builder（make_server 放的）。"""

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_PUT(self):
        self.route("PUT")

    def route(self, method):
        builder = self.server.builder
        url = urlsplit(self.path).path
        try:
            if method == "GET" and url == "/":
                return self.send_file(STATIC / "index.html")
            if method == "GET" and url.startswith("/static/"):
                return self.send_file(STATIC / unquote(url[len("/static/"):]))
            if url == "/api/areas":
                if method == "GET":
                    return self.send_json(builder.listing())
                if method == "POST":
                    return self.send_json(builder.create(self.body()), HTTPStatus.CREATED)
            m = AREA_URL.fullmatch(url)
            if m and method == "GET":
                return self.send_json(builder.read(unquote(m[1])))
            if m and method == "PUT":
                return self.send_json(builder.save(unquote(m[1]), self.body()))
            m = CHECK_URL.fullmatch(url)
            if m and method == "POST":
                name = unquote(m[1])
                builder.path(name)
                return self.send_json({"problems": builder.problems(name, self.body())})
            raise Problem(HTTPStatus.NOT_FOUND, f"沒有這個網址：{method} {url}")
        except Problem as e:
            self.send_json({"error": str(e)}, e.status)
        except OSError as e:                            # 例如存檔時資料夾不能寫
            log.exception(f"{method} {url} 失敗")
            self.send_json({"error": f"伺服器出錯：{e}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def body(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as e:
            raise Problem(HTTPStatus.BAD_REQUEST, f"不是正確的 JSON（{e}）")

    def send_file(self, path):
        path = path.resolve()
        # 只給 static 資料夾裡的檔，../ 跑出去的一律當成找不到
        if STATIC not in path.parents or not path.is_file() or path.suffix not in TYPES:
            raise Problem(HTTPStatus.NOT_FOUND, "找不到這個檔案")
        self.send(path.read_bytes(), TYPES[path.suffix])

    def send_json(self, value, status=HTTPStatus.OK):
        self.send(json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", status)

    def send(self, content, content_type, status=HTTPStatus.OK):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")   # 改了網頁檔案，瀏覽器才不會還在用舊的
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        log.debug(format % args)                        # 每個請求都印太吵，只在除錯時看


def make_server(host, port, folder):
    """開好（還沒開始跑）的伺服器；port 0 是讓系統挑一個空的（測試用）。"""
    server = ThreadingHTTPServer((host, port), Handler)
    server.builder = Builder(folder)
    return server
