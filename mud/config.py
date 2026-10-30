"""共用設定。"""
ENCODING = "cp950"   # Big5（微軟版，字比標準 Big5 多）
MAX_LINE = 1000      # 一行最多幾個 byte，跟 Diku 的 MAX_INPUT_LENGTH 一樣
PROMPT = "HP100> "
AREA_DIR = "areas"   # 區域檔的資料夾，跟 logs/ 同一層
START_ROOM = 101     # 登入後站的房間（遊戲裡的號碼：測試區域 100 ＋ 房間 1）
