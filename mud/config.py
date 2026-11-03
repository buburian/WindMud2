"""共用設定。"""
ENCODING = "cp950"   # Big5（微軟版，字比標準 Big5 多）
MAX_LINE = 1000      # 一行最多幾個 byte，跟 Diku 的 MAX_INPUT_LENGTH 一樣
PROMPT = "HP100> "
AREA_DIR = "areas"   # 區域檔的資料夾，跟 logs/ 同一層
START_ROOM = 101     # 登入後站的房間（遊戲裡的號碼：測試區域 100 ＋ 房間 1），要在世界區域裡
TICK_SECONDS = 30            # tick 的間隔（秒）：世界 tick（世界和全部動態區域共用）、每份副本自己的 tick
ROUND_SECONDS = 2            # 戰鬥一回合（秒），每場戰鬥從開打算起
RELEASE_SECONDS = 20 * 60    # 動態區域、副本沒有玩家超過這麼久（秒）就釋放
BUILDER_DIR = "builder_area"   # 區域編輯器存區域檔的資料夾，跟 areas/ 同一層
BUILDER_PORT = 1234            # 區域編輯器的網頁 port
