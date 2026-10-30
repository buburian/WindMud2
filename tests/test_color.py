from mud.color import colorize


def test_codes_use_c_colors():
    # 色碼跟 C 版 merc.h 一樣
    assert colorize("{M紫{x") == "\x1b[35;1m紫\x1b[0m"          # MAGENTA、NTEXT
    assert colorize("{G綠") == "\x1b[32;1m綠"                    # L_GREEN
    assert colorize("{r{R{y{Y{b{B{m{c{C{w{W{D{g") == (
        "\x1b[31m\x1b[31;1m\x1b[33m\x1b[33;1m\x1b[34m\x1b[34;1m\x1b[35m"
        "\x1b[36m\x1b[36;1m\x1b[37m\x1b[37;1m\x1b[30;1m\x1b[32m"
    )


def test_double_brace_prints_brace():
    assert colorize("{{M") == "{M"


def test_unknown_code_and_lone_brace_are_kept():
    assert colorize("{Q 和 {") == "{Q 和 {"
