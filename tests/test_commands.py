import mud.commands as commands
from mud.commands import system
from mud.config import ENCODING


class FakeWriter:
    """假的連線：只把送出的 bytes 收起來。"""

    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


def cast(writer, name, arg):
    pass


def channel(writer, name, arg):
    pass


def chat(writer, name, arg):
    pass


def test_first_command_starting_with_input_wins(monkeypatch):
    monkeypatch.setattr(commands, "COMMANDS", [("cast", cast), ("channel", channel), ("chat", chat)])
    assert commands.find("c") is cast
    assert commands.find("ch") is channel
    assert commands.find("cha") is channel
    assert commands.find("chat") is chat
    assert commands.find("x") is None


def test_order_decides_priority(monkeypatch):
    monkeypatch.setattr(commands, "COMMANDS", [("chat", chat), ("channel", channel)])
    assert commands.find("ch") is chat
    assert commands.find("chan") is channel


def test_real_table():
    assert commands.find("c") is system.do_chat
    assert commands.find("q") is system.do_quit


def test_quit_abbreviation_saves_and_disconnects(monkeypatch):
    saved = []
    monkeypatch.setattr(system, "save_player", saved.append)
    w = FakeWriter()
    assert commands.command(w, "小明", "q") is False
    assert saved == ["小明"]
    assert w.data == "再見。\r\n".encode(ENCODING)


def test_unknown_command():
    w = FakeWriter()
    assert commands.command(w, "小明", "xyz") is True
    assert w.data == "什麼？\r\nHP100> ".encode(ENCODING)
