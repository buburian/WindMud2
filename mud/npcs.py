"""NPC：沒有連線的角色。"""
from .characters import Character


class Npc(Character):
    """NPC。現在只有角色共同的部分；之後區域檔加了怪物，再補 NPC 自己的資料。"""
