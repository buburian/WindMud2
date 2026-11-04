// 生物、物品、重置用到的數字表，照 docs/區域製作手冊.md 的表抄的（畫面用的名字可以短一點）。
// tests/test_builder.py 會比對這裡的數字（或名稱）跟手冊的表：改手冊的表時要一起改這裡。
// 每一列是 [數字或名稱, 畫面上的名字, 滑鼠停上去的說明（可以沒有）]。

// 生物的行為旗標 act
export const ACT = [
  [1, "不是玩家", "C 版載入時自動加上，不用寫"],
  [2, "待在原地"],
  [4, "會撿地上的東西"],
  [32, "主動攻擊玩家"],
  [64, "不走出這個區域"],
  [128, "受傷會逃跑"],
];

// 生物身上的效果 affected_by
export const AFFECTED = [
  [1, "失明"],
  [2, "隱形"],
  [4, "看得出邪惡"],
  [8, "看得到隱形"],
  [16, "看得出魔法"],
];

export const SEXES = [
  [0, "中性"],
  [1, "男"],
  [2, "女"],
];

// 姿勢：也是角色現在狀態的定義
export const POSITIONS = [
  [0, "死了"],
  [1, "快死了"],
  [2, "不能動"],
  [3, "昏迷"],
  [4, "睡覺"],
  [5, "休息"],
  [6, "戰鬥中"],
  [7, "站著"],
];

// 生物的種類 tier（必填）
export const MOB_TIERS = [
  ["trash", "垃圾怪", "裝備完整度 ×0，經驗加成 ×0.1"],
  ["normal", "一般怪", "裝備完整度 ×0.5，經驗加成 ×1.2"],
  ["elite", "菁英怪", "裝備完整度 ×1，經驗加成 ×1.1"],
  ["boss", "Boss 怪", "裝備完整度 ×1.1，經驗加成 ×1.0"],
];

// 掉落裝備的顏色 drops 的 color；null 是不是裝備
export const ITEM_COLORS = [
  ["gray", "灰", "點數 ×0，沒有屬性"],
  ["white", "白", "點數 ×1"],
  ["blue", "藍", "點數 ×1.2"],
  ["purple", "紫", "點數 ×1.3"],
  ["orange", "橘", "點數 ×1.4"],
];

// 攻擊類型 attack：只用一種，或「主/次」兩種（主 70%、次 30%）；null 是純物理
export const ATTACK_TYPES = [
  ["phys", "物理"],
  ["spell", "法術"],
  ["dragon", "龍焰"],
];

// 攻防傾向 defense；null 是標準
export const DEFENSES = [
  ["phys", "物抗高"],
  ["spell", "法抗高"],
];

// 原型 archetype；null 是標準
export const ARCHETYPES = [
  ["tank", "坦克"],
  ["berserker", "狂戰"],
  ["agile", "敏捷"],
  ["extreme_tank", "極端坦克"],
];

// 種族：檔案裡寫名稱（C 版比對開頭，不分大小寫）
export const RACES = [
  ["human", "人類"],
  ["elf", "精靈"],
  ["halfelf", "半精靈"],
  ["drow", "暗精靈"],
  ["dwarf", "矮人"],
  ["halfdwarf", "半矮人"],
  ["hobbit", "妖精"],
  ["gnome", "侏儒"],
  ["faerie", "仙靈"],
  ["halfkobold", "半地精"],
  ["giant", "巨人"],
  ["ogre", "巨魔"],
  ["orc", "獸人"],
  ["kobold", "地精"],
  ["minotaur", "牛頭人"],
  ["troll", "洞穴巨人"],
  ["hobgoblin", "惡鬼"],
  ["insect", "昆蟲"],
  ["dragon", "飛龍"],
  ["animal", "動物"],
  ["god", "神族"],
  ["undead", "不死生物"],
  ["harpy", "人首鳥"],
  ["bear", "熊族"],
  ["githyanki", "吉仙奇"],
  ["elemental", "元素"],
  ["bat", "蝙蝠"],
  ["plant", "植物"],
  ["rat", "巨鼠"],
  ["vampire", "吸血鬼"],
  ["werewolf", "狼人"],
  ["goblin", "小惡鬼"],
  ["arachnid", "蜘蛛"],
  ["mindflayer", "掠心族"],
  ["object", "物品"],
  ["mist", "迷霧"],
  ["snake", "毒蛇"],
  ["worm", "毛蟲"],
  ["fish", "魚族"],
  ["hydra", "九頭龍"],
  ["lizard", "蜥蜴"],
];

// 平常的動作：什麼時候、怎麼做
export const ACTION_WHEN = [
  [0, "每個 tick"],
  [1, "有人走進房間"],
];

export const ACTION_MODE = [
  [0, "當成指令執行"],
  [1, "對整個房間顯示"],
  [2, "對走進來的人顯示"],
];

// 寫在程式裡的行為 special：[名稱, 畫面上的名字, "平常" 或 "戰鬥"]
export const SPECIALS = [
  ["spec_guard", "守衛", "平常"],
  ["spec_executioner", "劊子手", "平常"],
  ["spec_cast_adept", "幫新手施輔助法術", "平常"],
  ["spec_janitor", "撿垃圾", "平常"],
  ["spec_fido", "吃屍體", "平常"],
  ["spec_thief", "偷錢", "平常"],
  ["spec_mayor", "市長", "平常"],
  ["spec_repairman", "修門", "平常"],
  ["spec_breath_any", "隨機吐息", "戰鬥"],
  ["spec_breath_acid", "吐酸", "戰鬥"],
  ["spec_breath_fire", "吐火", "戰鬥"],
  ["spec_breath_frost", "吐冰", "戰鬥"],
  ["spec_breath_gas", "吐毒氣", "戰鬥"],
  ["spec_breath_lightning", "吐閃電", "戰鬥"],
  ["spec_cast_mage", "法師法術", "戰鬥"],
  ["spec_cast_cleric", "牧師法術", "戰鬥"],
  ["spec_cast_undead", "不死族法術", "戰鬥"],
  ["spec_cast_psionicist", "超能力者法術", "戰鬥"],
  ["spec_cast_judge", "high explosive", "戰鬥"],
  ["spec_cast_ghost", "鬼魂", "戰鬥"],
  ["spec_poison", "咬人下毒", "戰鬥"],
];

// 物品種類 item_type（商店的 buy_types 也用這張）
export const ITEM_TYPES = [
  [1, "照明用具"],
  [2, "卷軸"],
  [3, "魔杖"],
  [4, "魔棒"],
  [5, "武器"],
  [6, "弓", "C 版其實不能用這個種類：真正的弓是武器，values 第 1 個寫 6"],
  [8, "寶藏"],
  [9, "護具"],
  [10, "藥水"],
  [12, "家具"],
  [13, "垃圾"],
  [15, "容器"],
  [17, "液體容器"],
  [18, "鑰匙"],
  [19, "食物"],
  [20, "金錢"],
  [22, "船隻"],
  [23, "怪物屍體"],
  [24, "玩家屍體"],
  [25, "噴泉"],
  [26, "藥錠"],
];

// 物品 values 4 個欄位的名字，看物品種類。每個是 [名字, 寫法, 說明]：
// 寫法 number 數字、spell 法術名稱（存成文字）、attack 攻擊方式、liquid 液體、container 容器旗標、
// auto 由裝備等級算（作者不用寫，寫 0；畫面上不能改）
const AUTO_TIP = "由裝備等級算，不用寫（寫 0），見設計文件 §3.3";
const UNUSED = [["沒用到", "number"], ["沒用到", "number"], ["沒用到", "number"], ["沒用到", "number"]];
const UNKNOWN = [["不確定", "number"], ["不確定", "number"], ["不確定", "number"], ["不確定", "number"]];
const SPELLS = [["法術等級", "number"], ["法術 1", "spell"], ["法術 2", "spell"], ["法術 3", "spell"]];
const WAND = [["法術等級", "number"], ["可以用幾次", "number"], ["最多幾次", "number", "C 版放出時改成跟第 2 個一樣"], ["法術名稱", "spell"]];
export const VALUE_FIELDS = {
  1: [["不確定", "number"], ["不確定", "number"], ["可以亮幾小時", "number", "每個 tick 少 1，到 0 就燒完；寫負數永遠不會熄"], ["不確定", "number"]],
  2: SPELLS,
  3: WAND,
  4: WAND,
  5: [["武器類別", "number", "6 是弓，其他不確定"], ["傷害下限", "auto", AUTO_TIP], ["傷害上限", "auto", AUTO_TIP], ["攻擊方式", "attack"]],
  6: UNUSED,
  8: UNUSED,
  9: [["防護力", "auto", AUTO_TIP], ["耐久上限", "number", "C 版放出時改成價格"], ["防護上限", "auto", AUTO_TIP],
    ["特殊能力", "number", "穿在身上或披在身上寫 1 會飛；戴在頭上寫 1、2、3 分別是看得到隱形、看得到躲起來的人、看得出邪惡"]],
  10: SPELLS,
  12: UNUSED,
  13: UNUSED,
  15: [["容量", "number", "最多裝多重"], ["容器旗標", "container"], ["鑰匙", "number", "鑰匙的物品號碼，寫法同出口的 key，負數是沒有鑰匙"], ["封印的密碼", "number"]],
  17: [["容量", "number"], ["現在裝了多少", "number"], ["液體種類", "liquid"], ["有毒", "number", "不是 0 就是有毒"]],
  18: UNUSED,
  19: [["吃了會飽多少", "number"], ["不確定", "number"], ["不確定", "number"], ["有毒", "number", "不是 0 就是有毒"]],
  20: [["多少錢", "number", "C 版放出時改成價格"], ["不確定", "number"], ["不確定", "number"], ["不確定", "number"]],
  22: UNUSED,
  23: UNKNOWN,
  24: UNKNOWN,
  25: [["不確定", "number"], ["不確定", "number"], ["液體種類", "liquid"], ["不確定", "number"]],
  26: SPELLS,
};

// 物品的特性 extra_flags
export const EXTRA_FLAGS = [
  [1, "發亮"],
  [2, "低鳴"],
  [4, "黑暗"],
  [8, "鎖"],
  [16, "邪惡"],
  [32, "隱形"],
  [64, "魔法"],
  [128, "無法丟棄"],
  [256, "祝福"],
  [512, "雙手", "武器拿起來同時佔主手和副手；點數上限是兩格加起來"],
];

// 能不能拿起來、穿在哪裡 wear_flags（位置照 mud_design 設計文件 §3.3 的裝備欄位）
export const WEAR_FLAGS = [
  [1, "可以拿起來"],
  [2, "戒指"],
  [4, "頸"],
  [8, "身體"],
  [16, "頭"],
  [32, "腿"],
  [64, "腳"],
  [128, "手"],
  [256, "手臂"],
  [512, "副手", "盾牌或副手武器"],
  [1024, "披風"],
  [2048, "腰"],
  [4096, "手腕"],
  [8192, "主手"],
  [16384, "持握"],
];

// 物品的加成 affects 的 location
export const APPLY = [
  [0, "無"],
  [1, "力量"],
  [2, "敏捷"],
  [3, "智慧"],
  [4, "知識"],
  [5, "體質"],
  [6, "HP"],
  [7, "物理傷害"],
  [8, "法術傷害"],
  [9, "命中"],
  [10, "閃躲"],
  [11, "爆擊率"],
  [12, "爆擊傷害"],
  [13, "攻速"],
  [14, "物理抗性"],
  [15, "法術抗性"],
  [16, "龍焰抗性"],
];

// 武器 values 第 4 個：攻擊方式
export const ATTACKS = [
  [0, "重擊"],
  [1, "橫切"],
  [2, "戳刺"],
  [3, "重砍"],
  [4, "鞭打"],
  [5, "利爪"],
  [6, "鎚擊"],
  [7, "敲擊"],
  [8, "轟擊"],
  [9, "削割"],
  [10, "利牙"],
  [11, "突刺"],
  [12, "吸取"],
  [13, "橫劈"],
];

// 液體容器、噴泉 values 第 3 個：液體種類
export const LIQUIDS = [
  [0, "清水"],
  [1, "啤酒"],
  [2, "葡萄酒"],
  [3, "麥酒"],
  [4, "黑麥啤酒"],
  [5, "威士忌"],
  [6, "檸檬汁"],
  [7, "燒酒"],
  [8, "特產名酒"],
  [9, "發霉泥汁"],
  [10, "牛奶"],
  [11, "茶"],
  [12, "咖啡"],
  [13, "鮮血"],
  [14, "鹽水"],
  [15, "可樂"],
];

// 容器 values 第 2 個：容器旗標（加起來存成一個數字）
export const CONTAINER_FLAGS = [
  [1, "可以關起來"],
  [2, "撬不開"],
  [4, "關著"],
  [8, "鎖著"],
  [16, "可以封印"],
  [32, "封印著"],
];

// 重置 D：門一開始的狀態
export const DOOR_STATES = [
  [0, "開著"],
  [1, "關著"],
  [2, "關著而且鎖著"],
];

// 重置的指令
export const RESET_CMDS = [
  ["M", "放生物"],
  ["G", "給生物物品"],
  ["O", "放物品"],
  ["P", "放進容器"],
  ["D", "門的狀態"],
  ["R", "打亂出口"],
  ["*", "註解"],
];
