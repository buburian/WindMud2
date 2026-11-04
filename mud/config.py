"""共用設定。"""
ENCODING = "cp950"   # Big5（微軟版，字比標準 Big5 多）
MAX_LINE = 1000      # 一行最多幾個 byte，跟 Diku 的 MAX_INPUT_LENGTH 一樣
PROMPT = "HP100> "
AREA_DIR = "areas"   # 區域檔的資料夾，跟 logs/ 同一層
START_ROOM = 101     # 登入後站的房間（遊戲裡的號碼：測試區域 100 ＋ 房間 1），要在世界區域裡
# 定時做的事都用「每幾個 tick」定義（表在玩家角色手冊「定時做的事」）
TICK_SECONDS = 1             # 一個 tick 幾秒：世界 tick（世界和全部動態區域共用）、每份副本的 tick、每場戰鬥的 loop
ROUND_TICKS = 2              # 戰鬥一回合 ＝ 2 tick：打一輪、停一秒
HOUR_TICKS = 30              # 遊戲裡 1 小時（天氣走一格）＝ 30 tick
RELEASE_TICKS = 20 * 60      # 動態區域、副本連續這麼多 tick 沒有玩家就釋放（20 分鐘）
BUILDER_DIR = "builder_area"   # 區域編輯器存區域檔的資料夾，跟 areas/ 同一層
BUILDER_PORT = 1234            # 區域編輯器的網頁 port
