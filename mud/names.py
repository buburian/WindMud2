"""找名字的共用規則（使用者定的）：要找生物、物品的指令都用它（characters.find_in_room、objects.find），不要另外寫比對。

- 跟指令一樣只要打開頭：任何一個名字用輸入的字開頭就算，英文不分大小寫（do、DOG 都是 dog）。
- 同名的用「n.名字」：3.dog 是第 3 個對得上的（照 C 版的 number_argument）；0.dog、3. 找不到。
"""


def number_argument(text):
    """「3.dog」→ (3, "dog")；沒有點、或點前面不是數字 → (1, 原本的字)。"""
    number, dot, rest = text.partition(".")
    return (int(number), rest) if dot and number.isdecimal() else (1, text)


def pick(candidates, text, names_of):
    """candidates 裡（照它的順序）第 n 個名字對得上 text 的，找不到是 None。names_of(c) 是 c 的名字清單（小寫）。"""
    n, word = number_argument(text)
    word = word.lower()
    if n < 1 or not word:
        return None
    matches = [c for c in candidates if any(name.startswith(word) for name in names_of(c))]
    return matches[n - 1] if n <= len(matches) else None
