"""檢查區域檔的結構：uv run python -m mud.areacheck [檔案...]

沒給檔案就檢查 areas/ 全部；給檔案就只檢查那幾個。
只查一個檔時，通到別的區域的出口會去同一個資料夾的其他檔案找那間房。
有問題時結束代碼是 1，沒問題是 0。規則照 docs/區域製作手冊.md，寫在 area.check_files()。
"""
import sys
from pathlib import Path

from .area import check_files
from .config import AREA_DIR


def main(args=None):
    args = sys.argv[1:] if args is None else args
    if args:
        paths = [Path(a) for a in args]
        reference = sorted({p for path in paths for p in path.parent.glob("*.json")})
    else:
        paths = reference = sorted(Path(AREA_DIR).glob("*.json"))
    problems = check_files(paths, reference)
    total = 0
    for path in paths:
        found = problems[path]
        total += len(found)
        if found:
            print(f"✗ {path}：{len(found)} 個問題")
            for p in found:
                print(f"  - {p}")
        else:
            print(f"✓ {path}：沒問題")
    print(f"檢查了 {len(paths)} 個檔案，共 {total} 個問題")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
