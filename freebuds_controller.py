#!/usr/bin/env python3
# Copyright (c) 2026 Majaahh
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import json
import socket
import subprocess
import logging
import re
import hashlib
import io
import shutil
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from threading import RLock
from typing import Optional

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("freebuds")

SPP_CHANNEL = 16

SIDE_LEFT = 1
SIDE_RIGHT = 2

CRC16_TABLE = [
    0, 4129, 8258, 12387, 16516, 20645, 24774, 28903,
    -32504, -28375, -24246, -20117, -15988, -11859, -7730, -3601,
    4657, 528, 12915, 8786, 21173, 17044, 29431, 25302,
    -27847, -31976, -19589, -23718, -11331, -15460, -3073, -7202,
    9314, 13379, 1056, 5121, 25830, 29895, 17572, 21637,
    -23190, -19125, -31448, -27383, -6674, -2609, -14932, -10867,
    13907, 9842, 5649, 1584, 30423, 26358, 22165, 18100,
    -18597, -22662, -26855, -30920, -2081, -6146, -10339, -14404,
    18628, 22757, 26758, 30887, 2112, 6241, 10242, 14371,
    -13876, -9747, -5746, -1617, -30392, -26263, -22262, -18133,
    23285, 19156, 31415, 27286, 6769, 2640, 14899, 10770,
    -9219, -13348, -1089, -5218, -25735, -29864, -17605, -21734,
    27814, 31879, 19684, 23749, 11298, 15363, 3168, 7233,
    -4690, -625, -12820, -8755, -21206, -17141, -29336, -25271,
    32407, 28342, 24277, 20212, 15891, 11826, 7761, 3696,
    -97, -4162, -8227, -12292, -16613, -20678, -24743, -28808,
    -28280, -32343, -20022, -24085, -12020, -16083, -3762, -7825,
    4224, 161, 12482, 8419, 20484, 16421, 28742, 24679,
    -31815, -27752, -23557, -19494, -15555, -11492, -7297, -3234,
    689, 4752, 8947, 13010, 16949, 21012, 25207, 29270,
    -18966, -23093, -27224, -31351, -2706, -6833, -10964, -15091,
    13538, 9411, 5280, 1153, 29798, 25671, 21540, 17413,
    -22565, -18438, -30823, -26696, -6305, -2178, -14563, -10436,
    9939, 14066, 1681, 5808, 26199, 30326, 17941, 22068,
    -9908, -13971, -1778, -5841, -26168, -30231, -18038, -22101,
    22596, 18533, 30726, 26663, 6336, 2273, 14466, 10403,
    -13443, -9380, -5313, -1250, -29703, -25640, -21573, -17510,
    19061, 23124, 27191, 31254, 2801, 6864, 10931, 14994,
    -722, -4849, -8852, -12979, -16982, -21109, -25112, -29239,
    31782, 27655, 23652, 19525, 15522, 11395, 7392, 3265,
    -4321, -194, -12451, -8324, -20581, -16454, -28711, -24584,
    28183, 32310, 20053, 24180, 11923, 16050, 3793, 7920,
]  # fmt: skip


def crc16(data: bytes) -> int:
    crc = 0
    for b in data:
        idx = ((crc >> 8) ^ b) & 0xFF
        crc = (CRC16_TABLE[idx] ^ (crc << 8)) & 0xFFFF
    return crc


class Cmd:
    BATTERY = bytes([0x01, 0x08, 0x01, 0x00, 0x02, 0x00, 0x03, 0x00])
    VERSION = bytes([0x01, 0x07] + sum([[i, 0x00] for i in (*range(1, 13), 15)], []))
    CMD_01_1D = bytes([0x01, 0x1D, 0x01, 0x01, 0x01])

    GET_SERVICE_ABILITY = bytes([0x01, 0x02, 0x01, 0x00])
    GET_COMMAND_ABILITY = bytes([0x01, 0x03, 0x01, 0x00])

    @staticmethod
    def set_double_click(side: int, action: int) -> bytes:
        return bytes([0x01, 0x1F, side, 0x01, action])

    GET_DOUBLE_CLICK = bytes([0x01, 0x20, 0x03, 0x00])
    CLOUD_VERSION = bytes([0x09, 0x08])
    GET_OTA_PARAMS = bytes([0x09, 0x02, 0x01, 0x00])
    CANCEL_OTA = bytes([0x09, 0x08])
    CHECK_OTA_STATE = bytes([0x09, 0x01, 0x01, 0x00])
    LANGUAGE_PSI = bytes([0x0A, 0x0E, 0x02, 0x01, 0x00])
    GET_LANGUAGE = bytes([0x0C, 0x02, 0x01, 0x00, 0x02, 0x00, 0x03, 0x00])

    @staticmethod
    def set_language(lang_str: str) -> bytes:
        lang_bytes = lang_str.encode("us-ascii", errors="ignore")
        return bytes([0x0C, 0x01, 0x01, len(lang_bytes)]) + lang_bytes

    GET_GREET = bytes([0x2B, 0x0F, 0x01, 0x00])

    @staticmethod
    def set_greet(enable: bool) -> bytes:
        return bytes([0x2B, 0x0E, 0x01, 0x01, 0x01 if enable else 0x00])

    GET_WEAR = bytes([0x2B, 0x11, 0x01, 0x00])

    @staticmethod
    def set_wear(enable: bool) -> bytes:
        return bytes([0x2B, 0x10, 0x01, 0x01, 0x01 if enable else 0x00])

    GET_LONG_PRESS = bytes([0x2B, 0x17, 0x01, 0x00, 0x02, 0x00, 0x03, 0x00])

    @staticmethod
    def set_long_press(side: int, action: int) -> bytes:
        return bytes([0x2B, 0x16, side, 0x01, action])

    GET_SHORT_PRESS = bytes([0x2B, 0x21, 0x01, 0x00, 0x02, 0x00, 0x03, 0x00])

    @staticmethod
    def set_short_press(side: int, action: int) -> bytes:
        return bytes([0x2B, 0x20, side, 0x01, action])

    GET_SLIDE = bytes([0x2B, 0x1F, 0x01, 0x00, 0x02, 0x00, 0x03, 0x00])

    @staticmethod
    def set_slide(side: int, action: int) -> bytes:
        return bytes([0x2B, 0x1E, side, 0x01, action])

    GET_SAVING_MODE = bytes([0x2B, 0x1D, 0x01, 0x00])

    @staticmethod
    def set_saving_mode(enable: bool) -> bytes:
        return bytes([0x2B, 0x1C, 0x01, 0x01, 0x01 if enable else 0x00])

    GET_INTELLECT_VOLUME = bytes([0x2B, 0x23, 0x01, 0x00])

    @staticmethod
    def set_intellect_volume(enable: bool) -> bytes:
        return bytes([0x2B, 0x22, 0x01, 0x01, 0x01 if enable else 0x00])

    GET_ANC_STATE = bytes([0x2B, 0x05, 0x01, 0x00])
    GET_ANC_MODE_LEVEL = bytes([0x2B, 0x07, 0x01, 0x00])
    QUERY_NOISE_REDUCTION_MODE = bytes([0x2B, 0x2A, 0x01, 0x00])
    GET_NOISE_CONTROL = bytes([0x2B, 0x19, 0x01, 0x00, 0x02, 0x00])

    @staticmethod
    def set_anc_state(mode: int) -> bytes:
        return bytes([0x2B, 0x04, 0x01, 0x01, mode & 0xFF])

    @staticmethod
    def set_anc_state_level(mode: int, level: int = 0xFF) -> bytes:
        return bytes([0x2B, 0x04, 0x01, 0x02, mode & 0xFF, level & 0xFF])

    @staticmethod
    def set_anc_level(level: int) -> bytes:
        return bytes([0x2B, 0x08, 0x01, 0x01, level & 0xFF])

    @staticmethod
    def set_noise_control(left: Optional[int], right: Optional[int] = None) -> bytes:
        payload = bytearray((0x2B, 0x18))
        for tag, value in ((1, left), (2, right)):
            if value is not None:
                payload.extend((tag, 1, value))
        return bytes(payload)

    GET_EQ = bytes([0x2B, 0x4A, 0x02, 0x00])

    @staticmethod
    def set_eq(mode: int) -> bytes:
        return bytes([0x2B, 0x49, 0x01, 0x01, mode & 0xFF])

    GET_EQ_EXTENDED_SUPPORT = bytes([0x2B, 0xA8, 0x01, 0x01])

    GET_TRIPLE_CLICK = bytes([0x01, 0x26, 0x01, 0x00, 0x02, 0x00])

    @staticmethod
    def set_triple_click(left: int, right: int) -> bytes:
        payload = bytearray([0x01, 0x25])
        if left is not None:
            payload += bytes([0x01, 0x01, left & 0xFF])
        if right is not None:
            payload += bytes([0x02, 0x01, right & 0xFF])
        return bytes(payload)

    GET_DOUBLE_CLICK_MBB = bytes([0x01, 0x20, 0x01, 0x00, 0x02, 0x00])
    GET_DOUBLE_CLICK_CALL = bytes([0x01, 0x20, 0x04, 0x00])

    @staticmethod
    def set_double_click_mbb(left: int, right: int) -> bytes:
        payload = bytearray([0x01, 0x1F])
        if left is not None:
            payload += bytes([0x01, 0x01, left & 0xFF])
        if right is not None:
            payload += bytes([0x02, 0x01, right & 0xFF])
        return bytes(payload)

    @staticmethod
    def set_double_click_call(action: int) -> bytes:
        return bytes([0x01, 0x1F, 0x04, 0x01, action & 0xFF])

    GET_LONG_PRESS_MBB = bytes([0x2B, 0x17, 0x01, 0x00, 0x02, 0x00])
    GET_LONG_PRESS_CALL = bytes([0x2B, 0x17, 0x04, 0x00, 0x05, 0x00])

    @staticmethod
    def set_long_press_mbb(left: int, right: int) -> bytes:
        payload = bytearray([0x2B, 0x16])
        if left is not None:
            payload += bytes([0x01, 0x01, left & 0xFF])
        if right is not None:
            payload += bytes([0x02, 0x01, right & 0xFF])
        return bytes(payload)

    @staticmethod
    def set_long_press_call(action: int) -> bytes:
        return bytes([0x2B, 0x16, 0x04, 0x01, action & 0xFF])

    GET_SLIDE_MBB = bytes([0x2B, 0x1F, 0x01, 0x00, 0x02, 0x00])

    @staticmethod
    def set_slide_mbb(left: int, right: int) -> bytes:
        payload = bytearray([0x2B, 0x1E])
        if left is not None:
            payload += bytes([0x01, 0x01, left & 0xFF])
        if right is not None:
            payload += bytes([0x02, 0x01, right & 0xFF])
        return bytes(payload)

    GET_PINCH = bytes([0x2B, 0x21, 0x01, 0x00, 0x02, 0x00])

    @staticmethod
    def set_pinch(left: int, right: int) -> bytes:
        payload = bytearray([0x2B, 0x20])
        if left is not None:
            payload += bytes([0x01, 0x01, left & 0xFF])
        if right is not None:
            payload += bytes([0x02, 0x01, right & 0xFF])
        return bytes(payload)

    GET_LIGHT_HOLD = bytes([0x2B, 0x93, 0x01, 0x00, 0x02, 0x00])

    @staticmethod
    def set_light_hold(left: int, right: int) -> bytes:
        payload = bytearray([0x2B, 0x92])
        if left is not None:
            payload += bytes([0x01, 0x01, left & 0xFF])
        if right is not None:
            payload += bytes([0x02, 0x01, right & 0xFF])
        return bytes(payload)

    GET_GAME_LOW_LATENCY = bytes([0x2B, 0x6C, 0x02, 0x00])

    @staticmethod
    def set_game_low_latency(enable: bool) -> bytes:
        return bytes([0x2B, 0x6C, 0x01, 0x01, 0x01 if enable else 0x00])

    GET_DUAL_CONNECT = bytes([0x2B, 0x2F, 0x01, 0x00])

    @staticmethod
    def set_dual_connect(enable: bool) -> bytes:
        return bytes([0x2B, 0x2E, 0x01, 0x01, 0x01 if enable else 0x00])

    GET_TRANSLATE_MODE = bytes([0x2B, 0x4D, 0x01, 0x00])

    @staticmethod
    def set_translate_mode(enable: bool) -> bytes:
        return bytes([0x2B, 0x4C, 0x01, 0x01, 0x01 if enable else 0x00])

    GET_VOICE_ENHANCE = bytes([0x2B, 0x42, 0x01, 0x01])

    @staticmethod
    def set_voice_enhance(enable: bool) -> bytes:
        return bytes([0x2B, 0x41, 0x01, 0x01, 0x01 if enable else 0x00])

    GET_32K_HD = bytes([0x2B, 0x46, 0x01, 0x01])

    @staticmethod
    def set_32k_hd(enable: bool) -> bytes:
        return bytes([0x2B, 0x45, 0x01, 0x01, 0x01 if enable else 0x00])

    GET_HD_SWITCH = bytes([0x2B, 0xA3, 0x01, 0x01])

    @staticmethod
    def set_hd_switch(enable: bool) -> bytes:
        v = 0x01 if enable else 0x00
        return bytes([0x2B, 0xA2, 0x01, 0x01, v])

    GET_LEFT_RIGHT_EAR = bytes([0x2B, 0x9A, 0x01, 0x00])

    @staticmethod
    def set_left_right_ear(enable: bool) -> bytes:
        return bytes([0x2B, 0x99, 0x01, 0x01, 0x01 if enable else 0x00])

    GET_WIND_MODE = bytes([0x2B, 0x95, 0x01, 0x01])

    @staticmethod
    def set_wind_mode(enable: bool) -> bytes:
        return bytes([0x2B, 0x94, 0x01, 0x01, 0x01 if enable else 0x00])

    GET_WEARING_STATUS = bytes([0x2B, 0x25, 0x01, 0x00, 0x02, 0x00])
    GET_DORMANT_TIME = bytes([0x2B, 0x48, 0x01, 0x00])

    @staticmethod
    def set_dormant_time(option: int, seconds: int) -> bytes:
        ts = seconds.to_bytes(4, "big")
        return bytes([0x2B, 0x47, 0x01, 0x01, option & 0xFF, 0x01, 0x04]) + ts

    GET_SILENT_UPGRADE = bytes([0x2B, 0x70, 0x01, 0x01])

    @staticmethod
    def set_silent_upgrade(enable: bool) -> bytes:
        return bytes([0x2B, 0x6F, 0x01, 0x01, 0x01 if enable else 0x00])

    GET_BT_MAIN_STATUS = bytes([0x2B, 0x6A, 0x01, 0x01])
    GET_CLOSE_COVER_REMIND = bytes([0x2B, 0x7F, 0x01, 0x01])
    GET_MUSIC_MODE = bytes([0x2B, 0x53, 0x02, 0x00])
    GET_HEALTH_ALERTS = bytes([0x2B, 0x61, 0x01, 0x00])

    @staticmethod
    def set_health_alerts(enable: bool) -> bytes:
        return bytes([0x2B, 0x60, 0x01, 0x01, 0x01 if enable else 0x00])

    FACTORY_RESET = bytes([0x01, 0x0D, 0x01, 0x01, 0x01])
    GET_AMBIENT_SOUND = bytes([0x2B, 0x2C, 0x01, 0x00])
    GET_CONNECT_ABILITY = bytes([0x2B, 0x2D, 0x01, 0x00])
    QUERY_PAIR = bytes([0x2B, 0x8F, 0x01, 0x00])
    STATE_PAIR = bytes([0x2B, 0x90, 0x01, 0x01, 0x01])
    GET_DEVICES_BONDED = bytes([0x2B, 0x31, 0x01, 0x00])

    @staticmethod
    def get_bonded_by_index(index: int) -> bytes:
        return bytes([0x2B, 0x31, 0x03, 0x01, index & 0xFF])

    @staticmethod
    def get_bonded_by_mac(mac: bytes) -> bytes:
        return bytes([0x2B, 0x31, 0x04, 0x06]) + mac

    @staticmethod
    def set_primary_device(mac: bytes) -> bytes:
        return bytes([0x2B, 0x32, 0x01, 0x06]) + mac

    @staticmethod
    def single_device_setting(sub: int, mac: bytes) -> bytes:
        return bytes([0x2B, 0x33, sub & 0xFF, 0x06]) + mac

    GET_FIT_CHECK = bytes([0x2B, 0x26, 0x01, 0x00])
    EXIT_FIT_CHECK = bytes([0x2B, 0x26, 0x03, 0x00])
    GET_FIT_DETECT_VERSION = bytes([0x2B, 0x37, 0x01, 0x00])
    HEARTBEAT = bytes([0x2B, 0x4E, 0x01, 0x00])

    SET_TIME = None


GESTURE_ACTIONS = {
    0: "None/Default",
    1: "Voice assistant",
    2: "Noise control",
    3: "Previous track",
    4: "Next track",
    5: "Volume up",
    6: "Volume down",
    7: "Play/Pause",
    8: "Answer call",
}

DC_ACTIONS = {
    0: "Voice assistant",
    1: "Play/Pause",
    2: "Next track",
    7: "Previous track",
    255: "None",
}

LP_ACTIONS = {
    10: "Noise control",
    14: "Song recognition",
    15: "Freestyle listen",
    255: "None",
}

TRIPLE_ACTIONS = {2: "Next track", 7: "Previous track", 255: "None"}
SLIDE_ACTIONS = {0: "Volume", 255: "None"}
CALL_ACTIONS = {
    "long_press": {0: "Reject call", 255: "None"},
    "double_click": {0: "Answer/End call", 255: "None"},
}

PINCH_ACTIONS = {
    0: "Face-to-face translate",
    1: "Voice memo",
    2: "Pairing",
    3: "Freestyle listen",
    4: "Pinch chat",
    5: "Song recognition",
    255: "None",
}

ACTION_NOISE_CONTROL = {
    "long_press": 10,
}

NOISE_CYCLES = {
    1: "Noise cancelling / Off",
    2: "Noise cancelling / Off / Awareness",
    3: "Noise cancelling / Awareness",
    4: "Off / Awareness",
}

CALL_SETTERS = {
    "double_click": Cmd.set_double_click_call,
    "long_press": Cmd.set_long_press_call,
}

ACTION_RESULT = {
    0: "Left OK",
    1: "Left failed",
    2: "Right OK",
    3: "Right failed",
}

NC_MODE_OFF = 0
NC_MODE_ON = 1
NC_MODE_AWARE = 2

NC_MODES = {
    NC_MODE_OFF: "Off",
    NC_MODE_ON: "On",
    NC_MODE_AWARE: "Awareness",
}
NC_MODE_ALIASES = {
    "off": NC_MODE_OFF,
    "0": NC_MODE_OFF,
    "cancel": NC_MODE_OFF,
    "on": NC_MODE_ON,
    "noise": NC_MODE_ON,
    "1": NC_MODE_ON,
    "aware": NC_MODE_AWARE,
    "awareness": NC_MODE_AWARE,
    "transparent": NC_MODE_AWARE,
    "pass": NC_MODE_AWARE,
    "pass_through": NC_MODE_AWARE,
    "2": NC_MODE_AWARE,
}

NC_LEVEL_GENERAL = 0
NC_LEVEL_COZY = 1
NC_LEVEL_ULTRA = 2
NC_LEVEL_DYNAMIC = 3

NC_LEVELS = {
    NC_LEVEL_GENERAL: "General",
    NC_LEVEL_COZY: "Cozy",
    NC_LEVEL_ULTRA: "Ultra",
    NC_LEVEL_DYNAMIC: "Dynamic",
}
NC_LEVEL_ALIASES = {
    "general": NC_LEVEL_GENERAL,
    "balance": NC_LEVEL_GENERAL,
    "0": NC_LEVEL_GENERAL,
    "cozy": NC_LEVEL_COZY,
    "comfortable": NC_LEVEL_COZY,
    "light": NC_LEVEL_COZY,
    "1": NC_LEVEL_COZY,
    "ultra": NC_LEVEL_ULTRA,
    "deep": NC_LEVEL_ULTRA,
    "deeply": NC_LEVEL_ULTRA,
    "depth": NC_LEVEL_ULTRA,
    "2": NC_LEVEL_ULTRA,
    "dynamic": NC_LEVEL_DYNAMIC,
    "ai": NC_LEVEL_DYNAMIC,
    "smart": NC_LEVEL_DYNAMIC,
    "3": NC_LEVEL_DYNAMIC,
}


def resolve_anc_level(value) -> Optional[int]:
    if isinstance(value, int):
        return value if value in NC_LEVELS else None
    if isinstance(value, str):
        return NC_LEVEL_ALIASES.get(value.strip().lower())
    return None


EQ_MODE_DEFAULT = 1
EQ_MODE_BASS = 2
EQ_MODE_TREBLE = 3
EQ_MODE_VOICES = 9

EQ_MODES = {
    EQ_MODE_DEFAULT: "Default",
    EQ_MODE_BASS: "Bass boost",
    EQ_MODE_TREBLE: "Treble boost",
    EQ_MODE_VOICES: "Voices",
}
EQ_MODE_ALIASES = {
    "default": EQ_MODE_DEFAULT,
    "balanced": EQ_MODE_DEFAULT,
    "1": EQ_MODE_DEFAULT,
    "bass": EQ_MODE_BASS,
    "bassboost": EQ_MODE_BASS,
    "2": EQ_MODE_BASS,
    "treble": EQ_MODE_TREBLE,
    "trebleboost": EQ_MODE_TREBLE,
    "3": EQ_MODE_TREBLE,
    "voices": EQ_MODE_VOICES,
    "voice": EQ_MODE_VOICES,
    "clearvoice": EQ_MODE_VOICES,
    "9": EQ_MODE_VOICES,
}


def resolve_eq_mode(value) -> Optional[int]:
    if isinstance(value, int):
        return value if value in EQ_MODES else None
    if isinstance(value, str):
        return EQ_MODE_ALIASES.get(value.strip().lower())
    return None


_CMD_NAMES = {
    "help", "bat", "ver", "info", "find",
    "fit", "gesture", "cycle", "anc", "nc", "sfx", "lang", "raw", "misc",
    "devices", "dev",
}  # fmt: skip

GESTURE_TYPES = {
    "long_press": {
        "name": "Long press",
        "aliases": ("lp", "long"),
        "get": Cmd.GET_LONG_PRESS_MBB,
        "set": Cmd.set_long_press_mbb,
        "svc": 0x2B,
        "cmd": 0x17,
        "set_cmd": 0x16,
        "actions": LP_ACTIONS,
    },
    "slide": {
        "name": "Slide",
        "aliases": ("slide", "sl"),
        "get": Cmd.GET_SLIDE_MBB,
        "set": Cmd.set_slide_mbb,
        "svc": 0x2B,
        "cmd": 0x1F,
        "set_cmd": 0x1E,
        "actions": SLIDE_ACTIONS,
    },
    "double_click": {
        "name": "Double click",
        "aliases": ("dc", "double"),
        "get": Cmd.GET_DOUBLE_CLICK_MBB,
        "set": Cmd.set_double_click_mbb,
        "svc": 0x01,
        "cmd": 0x20,
        "set_cmd": 0x1F,
        "actions": DC_ACTIONS,
    },
    "triple_click": {
        "name": "Triple click",
        "aliases": ("triple", "tri", "tc"),
        "get": Cmd.GET_TRIPLE_CLICK,
        "set": Cmd.set_triple_click,
        "svc": 0x01,
        "cmd": 0x26,
        "set_cmd": 0x25,
        "actions": TRIPLE_ACTIONS,
    },
}

GESTURE_ALIASES = {}
for _gkey, _gtype in GESTURE_TYPES.items():
    GESTURE_ALIASES[_gkey] = _gkey
    for _alias in _gtype["aliases"]:
        GESTURE_ALIASES[_alias] = _gkey

_CMD_NAMES.update(GESTURE_ALIASES)

FEATURES = {
    "wear": {
        "name": "Wear detection",
        "get": "get_wear_setting",
        "set": "set_wear",
    },
    "glat": {
        "name": "Game low latency",
        "get": "get_game_low_latency",
        "set": "set_game_low_latency",
    },
    "dual": {
        "name": "Dual connect",
        "get": "get_dual_connect",
        "set": "set_dual_connect",
    },
    "venh": {
        "name": "Voice enhance",
        "get": "get_voice_enhance",
        "set": "set_voice_enhance",
    },
    "hd": {
        "name": "Prioritize sound quality",
        "get": "get_hd_switch",
        "set": "set_hd_switch",
    },
    "wind": {
        "name": "Wind mode",
        "get": "get_wind_mode",
        "set": "set_wind_mode",
    },
    "silent": {
        "name": "Silent upgrade",
        "get": "get_silent_upgrade",
        "set": "set_silent_upgrade",
    },
    "health": {
        "name": "Health alerts",
        "get": "get_health_alerts",
        "set": "set_health_alerts",
    },
    "dynamic": {"name": "Dynamic ANC capability", "get": "get_dynamic_anc_support"},
    "wearst": {"name": "Wearing status", "get": "get_wearing_status"},
    "btmain": {"name": "BT main status", "get": "get_bt_main_status"},
    "music": {"name": "Music mode", "get": "get_music_mode"},
    "ambient": {"name": "Ambient sound", "get": "get_ambient_sound"},
    "conn": {"name": "Connect ability", "get": "get_connect_ability"},
}


def print_status(label: str, status: int) -> None:
    if status == 100003:
        print(f"{label}: Not supported by device")
    else:
        print(f"{label}: status=0x{status:08X}")


def build_frame(cmd_payload: bytes) -> bytes:
    total_len = len(cmd_payload)
    frame_len = total_len + 1
    frame = bytearray(4 + total_len + 2)
    frame[0] = 0x5A
    frame[1] = (frame_len >> 8) & 0xFF
    frame[2] = frame_len & 0xFF
    frame[3] = 0x00
    frame[4 : 4 + total_len] = cmd_payload
    crc_val = crc16(bytes(frame[: 4 + total_len]))
    frame[4 + total_len] = (crc_val >> 8) & 0xFF
    frame[4 + total_len + 1] = crc_val & 0xFF
    return bytes(frame)


def parse_frames(data: bytes) -> list[dict]:
    frames = []
    offset = 0
    while offset < len(data):
        if data[offset] != 0x5A:
            offset += 1
            continue
        remaining = data[offset:]
        if len(remaining) < 4:
            break
        frame_len = (remaining[1] << 8) | remaining[2]
        total = 4 + (frame_len - 1) + 2
        if len(remaining) < total:
            break
        frame_data = remaining[:total]
        payload = frame_data[4 : 4 + (frame_len - 1)]
        crc_recv = (frame_data[-2] << 8) | frame_data[-1]
        crc_calc = crc16(frame_data[:-2])
        frames.append(
            {
                "payload": payload,
                "svc": payload[0] if len(payload) > 0 else 0,
                "cmd": payload[1] if len(payload) > 1 else 0,
                "data": payload[2:] if len(payload) > 2 else b"",
                "crc_ok": crc_recv == crc_calc,
            }
        )
        offset += total
    return frames


def parse_tlv(data: bytes) -> list[dict]:
    entries = []
    pos = 0
    while pos < len(data) - 1:
        tag = data[pos]
        length = data[pos + 1]
        if pos + 2 + length > len(data):
            break
        value = data[pos + 2 : pos + 2 + length]
        entries.append({"tag": tag, "len": length, "value": value})
        pos += 2 + length
    return entries


def mac_to_bytes(mac: str) -> bytes:
    return bytes.fromhex(mac.replace(":", "").replace("-", ""))


def mac_to_str(raw: bytes) -> str:
    if len(raw) != 6:
        return raw.hex()
    return ":".join(f"{b:02X}" for b in raw)


FIT_RESOURCE_URL = (
    "https://contentcenter-dre.dbankcdn.cn/pub_1/HW-SmartHome_oem_900_9/"
    "b0/v3/eu/device/guide/000145/000145_01.zip"
)
FIT_AUDIO_HASH = "dcdb02ba6eb810f19cb6a298fd53c3fa7e22a47076aea86a062ce3c8bbbf9ed3"


def fit_audio() -> Path:
    destination = Path.home() / ".cache" / "freebuds-controller" / "detect_music.ogg"
    if (
        destination.is_file()
        and hashlib.sha256(destination.read_bytes()).hexdigest() == FIT_AUDIO_HASH
    ):
        return destination
    with urllib.request.urlopen(FIT_RESOURCE_URL, timeout=30) as response:
        with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
            audio = archive.read("000145_01/detect_music.ogg")
    if hashlib.sha256(audio).hexdigest() != FIT_AUDIO_HASH:
        raise ValueError("Unexpected Huawei fit-test audio checksum")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
        stream.write(audio)
    Path(stream.name).replace(destination)
    return destination


class FreeBudsController:
    def __init__(self, mac_address: str = None):
        self.mac_address = mac_address
        self.sock = None
        self._connected = False
        self._lock = RLock()

    def connect(self, mac_address: str = None, channel: int = SPP_CHANNEL) -> bool:
        if mac_address:
            self.mac_address = mac_address
        if not self.mac_address:
            log.error("No MAC address")
            return False

        mac = self.mac_address.upper().replace("-", ":")
        if not re.match(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$", mac):
            raise ValueError(f"Invalid MAC: {mac_address}")

        log.debug(f"Connecting SPP to {mac} (channel {channel})...")
        try:
            self.sock = socket.socket(
                socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
            )
            self.sock.settimeout(10)
            self.sock.connect((mac, channel))
            self._connected = True
            log.debug("Connected")
            return True
        except Exception as e:
            log.error(f"Connect failed: {e}")
            self._connected = False
            return False

    def disconnect(self):
        with self._lock:
            if self.sock:
                try:
                    self.sock.close()
                except OSError:
                    pass
                self.sock = None
            self._connected = False
        log.debug("Disconnected")

    def send_command(self, cmd_payload: bytes, read_timeout: float = 2.0) -> list[dict]:
        if not self._connected or not self.sock:
            log.error("Not connected")
            return []

        with self._lock:
            try:
                frame = build_frame(cmd_payload)
                log.debug(f">> {frame.hex()}")
                self.sock.sendall(frame)

                response = b""
                self.sock.settimeout(read_timeout)
                while True:
                    try:
                        chunk = self.sock.recv(4096)
                        if not chunk:
                            break
                        response += chunk
                        log.debug(f"<< {chunk.hex()}")
                    except socket.timeout:
                        break

                return [f for f in parse_frames(response) if f["crc_ok"]]

            except Exception as e:
                log.error(f"Send error: {e}")
                self._connected = False
                return []

    def _match_frame(self, frames: list[dict], svc: int, cmd: int) -> Optional[dict]:
        for f in frames:
            if f["svc"] == svc and f["cmd"] == cmd:
                return f
        return None

    def _extract_byte_at(self, data: bytes, offset: int) -> Optional[int]:
        if offset < len(data):
            return data[offset]
        return None

    def _extract_tlv_value(self, data: bytes, target_tag: int) -> Optional[bytes]:
        for tlv in parse_tlv(data):
            if tlv["tag"] == target_tag:
                return tlv["value"]
        return None

    def _is_status_response(self, data: bytes) -> bool:
        return len(data) >= 6 and data[0] == 0x7F and data[1] == 0x04

    def _parse_status_code(self, data: bytes) -> Optional[int]:
        if self._is_status_response(data) and len(data) >= 6:
            return (data[2] << 24) | (data[3] << 16) | (data[4] << 8) | data[5]
        return None

    def get_battery(self) -> Optional[dict]:
        frames = self.send_command(Cmd.BATTERY)
        f = self._match_frame(frames, 0x01, 0x08)
        if not f:
            log.warning("No battery frame found")
            return None

        val = self._extract_tlv_value(f["data"], 2)
        if val and len(val) >= 3:
            bat = {
                "left_battery": val[0],
                "right_battery": val[1],
                "box_battery": val[2],
            }
            charging = self._extract_tlv_value(f["data"], 3) or b""
            for side, state in zip(("left", "right", "box"), charging):
                bat[side + "_charging"] = bool(state)
            in_box = self._extract_tlv_value(f["data"], 5) or b""
            for side, state in zip(("left", "right"), in_box):
                if state in (0, 1):
                    bat[side + "_in_box"] = bool(state)
            log.debug(
                f"Battery: L={bat['left_battery']}% "
                f"R={bat['right_battery']}% Box={bat['box_battery']}%"
            )
            return bat
        log.warning("Battery: no tag=2 found in TLV")
        return None

    def get_version(self) -> Optional[dict]:
        frames = self.send_command(Cmd.VERSION)
        f = self._match_frame(frames, 0x01, 0x07)
        if not f:
            log.warning("No version frame found")
            return None

        known = {
            3: "model",
            7: "firmware",
            9: "serial",
            10: "bt_version",
            15: "bt_prefix",
            24: "bud_serials",
        }
        result = {}
        for tlv in parse_tlv(f["data"]):
            tag = tlv["tag"]
            try:
                val = (
                    tlv["value"].decode("utf-8", errors="ignore").strip().rstrip("\x00")
                )
                if val and len(val) < 100:
                    key = known.get(tag, f"field_{tag}")
                    result[key] = val
                    if tag == 15:
                        result["ota_package"] = val
                    if key == "firmware":
                        log.debug(f"Firmware: {val}")
            except Exception:
                pass

        if result:
            return result
        log.warning("Version: no parseable data")
        return None

    def _parse_bool_get(
        self, frames: list[dict], svc: int, cmd_get: int, cmd_set: int, name: str
    ) -> Optional[dict]:

        f = self._match_frame(frames, svc, cmd_get)
        if not f:
            f = self._match_frame(frames, svc, cmd_set)
        if not f:
            log.warning(f"No {name} response")
            return None

        data = f["data"]

        status = self._parse_status_code(data)
        if status is not None:
            result = {
                "status": status,
                "status_ok": status == 100000,
                "raw": data.hex(),
            }
            if status == 100000:
                log.debug(f"{name}: status OK")
            else:
                log.debug(f"{name}: status=0x{status:08X}")
            return result

        val = self._extract_byte_at(data, 2)
        if val is not None and val in (0, 1):
            result = {"enabled": val == 1}
            log.debug(f"{name}: {'On' if result['enabled'] else 'Off'}")
            return result

        tlvs = parse_tlv(data)
        for tlv in tlvs:
            if len(tlv["value"]) == 1 and tlv["value"][0] in (0, 1):
                result = {"enabled": tlv["value"][0] == 1}
                log.debug(
                    f"{name}: {'On' if result['enabled'] else 'Off'} (from TLV tag {tlv['tag']})"
                )
                return result

        log.warning(f"{name}: unrecognized response format (data={data.hex()})")
        return {"raw": data.hex()}

    def get_greet_setting(self) -> Optional[dict]:
        return self._parse_bool_get(
            self.send_command(Cmd.GET_GREET), 0x2B, 0x0F, 0x0E, "Greet (voice prompt)"
        )

    def set_greet(self, enable: bool) -> Optional[dict]:
        result = self._send_bool_setter(
            Cmd.set_greet(enable), 0x2B, 0x0E, "Greet (voice prompt)", enable
        )
        return result

    def get_wear_setting(self) -> Optional[dict]:
        return self._parse_bool_get(
            self.send_command(Cmd.GET_WEAR), 0x2B, 0x11, 0x10, "Wear detection"
        )

    def set_wear(self, enable: bool) -> Optional[dict]:
        result = self._send_bool_setter(
            Cmd.set_wear(enable), 0x2B, 0x10, "Wear detection", enable
        )
        return result

    def get_intellect_volume(self) -> Optional[dict]:
        return self._parse_bool_get(
            self.send_command(Cmd.GET_INTELLECT_VOLUME),
            0x2B,
            0x23,
            0x22,
            "Intellect volume",
        )

    def set_intellect_volume(self, enable: bool) -> Optional[dict]:
        result = self._send_bool_setter(
            Cmd.set_intellect_volume(enable), 0x2B, 0x22, "Intellect volume", enable
        )
        return result

    def get_saving_mode(self) -> Optional[dict]:
        return self._parse_bool_get(
            self.send_command(Cmd.GET_SAVING_MODE), 0x2B, 0x1D, 0x1C, "Saving mode"
        )

    def set_saving_mode(self, enable: bool) -> Optional[dict]:
        result = self._send_bool_setter(
            Cmd.set_saving_mode(enable), 0x2B, 0x1C, "Saving mode", enable
        )
        return result

    def _parse_touch_get(
        self, frames: list[dict], svc: int, cmd: int, name: str, actions: dict
    ) -> Optional[dict]:

        f = self._match_frame(frames, svc, cmd)
        if not f:
            log.warning(f"No {name} response")
            return None

        data = f["data"]

        status = self._parse_status_code(data)
        if status is not None:
            if status == 100000:
                log.debug(f"{name}: not configured (status=OK, value=100000)")
            else:
                log.debug(f"{name}: status response code={status} (0x{status:08X})")
            return {"status": status, "status_ok": status == 100000, "raw": data.hex()}

        result = {"raw": data.hex()}
        found = False
        for tlv in parse_tlv(data):
            v = tlv["value"]
            if tlv["tag"] == 1 and len(v) == 1:
                result["left"] = v[0]
                result["left_name"] = actions.get(v[0], f"Unknown ({v[0]})")
                found = True
            elif tlv["tag"] == 2 and len(v) == 1:
                result["right"] = v[0]
                result["right_name"] = actions.get(v[0], f"Unknown ({v[0]})")
                found = True
            elif tlv["tag"] == 3:
                result["supported"] = list(v)
                result["supported_names"] = [
                    actions.get(b, f"Unknown ({b})") for b in result["supported"]
                ]
                found = True
            elif tlv["tag"] == 4 and len(v) == 1:
                result["call_action"] = v[0]
                found = True
            elif tlv["tag"] == 6:
                result["call_supported"] = list(v)
                found = True

        if found:
            log.debug(f"{name}: {result}")
            return result

        log.warning(f"{name}: unrecognized response format (data={data.hex()})")
        return None

    def _send_touch_set(
        self,
        cmd_payload: bytes,
        svc: int,
        cmd: int,
        name: str,
        side: int,
        action: int,
        actions: dict,
    ) -> Optional[dict]:

        frames = self.send_command(cmd_payload)
        f = self._match_frame(frames, svc, cmd)
        if not f:
            log.warning(f"No {name} set response")
            return None

        data = f["data"]
        side_name = {0: "Both", 1: "Left", 2: "Right"}[side]
        action_name = actions.get(action, f"Unknown ({action})")
        result = {
            "side": side,
            "side_name": side_name,
            "action": action,
            "action_name": action_name,
        }

        status = self._parse_status_code(data)
        if status is not None:
            ok = status == 100000
            result["success"] = ok
            result["status"] = status
            if ok:
                log.debug(f"{name}: {side_name} -> {action_name}")
            else:
                log.warning(f"{name}: set failed (status=0x{status:08X})")
            return result

        for tlv in parse_tlv(data):
            if (
                tlv["tag"] == (6 if cmd_payload[2] == 4 else 3)
                and len(tlv["value"]) == 1
            ):
                code = tlv["value"][0]
                ok = (
                    code in (0, 2)
                    if side == 0
                    else code == (2 if side == SIDE_RIGHT else 0)
                )
                result["success"] = ok
                result["result"] = code
                result["result_name"] = ACTION_RESULT.get(code, f"Unknown ({code})")
                if ok:
                    log.debug(
                        f"{name}: {side_name} -> {action_name} "
                        f"(result={ACTION_RESULT.get(code)})"
                    )
                else:
                    log.warning(f"{name}: set failed ({ACTION_RESULT.get(code, code)})")
                return result

        echo = self._extract_tlv_value(data, cmd_payload[2])
        if echo and len(echo) == 1:
            resp_action = echo[0]
            result["success"] = resp_action == action
            if result["success"]:
                log.debug(f"{name}: {side_name} -> {action_name}")
            else:
                log.warning(f"{name}: set may have failed (resp={resp_action})")
            return result

        result["success"] = None
        log.warning(f"{name}: unrecognized set response (resp={data.hex()})")
        return result

    def _send_bool_setter(
        self, cmd_payload: bytes, svc: int, cmd: int, name: str, enable: bool
    ) -> Optional[dict]:

        frames = self.send_command(cmd_payload)
        f = self._match_frame(frames, svc, cmd)
        if not f:
            log.warning(f"No {name} set response")
            return None

        data = f["data"]

        status = self._parse_status_code(data)
        if status is not None:
            ok = status == 100000
            result = {"enabled": enable, "success": ok, "status": status}
            if ok:
                log.info(f"{name}: set to {'On' if enable else 'Off'}")
            else:
                log.warning(f"{name}: set failed (status=0x{status:08X})")
            return result

        return {"enabled": enable, "success": None, "raw": data.hex()}

    def _get_touch_gesture(self, key: str) -> Optional[dict]:
        gtype = GESTURE_TYPES[key]
        state = self._parse_touch_get(
            self.send_command(gtype["get"] + b"\x03\x00"),
            gtype["svc"],
            gtype["cmd"],
            gtype["name"],
            gtype["actions"],
        )

        if state and "supported" in state:
            advertised = state["supported"]
            state["advertised"] = advertised
            state["supported"] = [
                v
                for v in gtype["actions"]
                if v in advertised or (key == "long_press" and v == 255)
            ]
            state["supported_names"] = [gtype["actions"][v] for v in state["supported"]]
        if state and key in CALL_ACTIONS and "call_action" in state:
            state["call_name"] = CALL_ACTIONS[key].get(state["call_action"], "Unknown")
        if key == "slide" and state and "left" in state:
            state["global"] = state.pop("left")
            state["global_name"] = state.pop("left_name")
            state.pop("right", None)
            state.pop("right_name", None)
        return state

    def set_call_gesture(self, gesture: str, action: int) -> Optional[dict]:
        key = GESTURE_ALIASES.get(gesture.lower())
        if key not in CALL_SETTERS:
            return None
        state = self._get_touch_gesture(key)
        if (
            not state
            or action not in CALL_ACTIONS[key]
            or action not in state.get("call_supported", ())
        ):
            return None
        entry = GESTURE_TYPES[key]
        result = self._send_touch_set(
            CALL_SETTERS[key](action),
            entry["svc"],
            entry["set_cmd"],
            entry["name"],
            0,
            action,
            CALL_ACTIONS[key],
        )

        if result and result.get("success") is not False:
            observed = self._get_touch_gesture(key) or {}
            result["success"] = observed.get("call_action") == action
        return result

    def _set_touch_gesture(self, key: str, side: int, action: int) -> Optional[dict]:
        gtype = GESTURE_TYPES[key]
        left = action if side in (0, SIDE_LEFT) else None
        right = action if side == SIDE_RIGHT else None
        if key == "slide" and side == 0:
            payload = bytes([0x2B, 0x1E, 1, 1, action, 2, 2, action])
        else:
            payload = gtype["set"](left, right)
        result = self._send_touch_set(
            payload,
            gtype["svc"],
            gtype["set_cmd"],
            gtype["name"],
            side,
            action,
            gtype["actions"],
        )

        if result and result.get("success") is not False:
            observed = self._get_touch_gesture(key) or {}
            field = {0: "global", 1: "left", 2: "right"}[side]
            result["success"] = observed.get(field) == action
        return result

    def get_gesture_action(self, gesture_type: str) -> Optional[dict]:
        key = GESTURE_ALIASES.get(gesture_type.lower())
        if not key:
            log.error(
                f"Unknown gesture '{gesture_type}'. Valid: {', '.join(GESTURE_ALIASES)}"
            )
            return None
        return self._get_touch_gesture(key)

    def set_gesture_action(
        self, gesture_type: str, side: int, action: int
    ) -> Optional[dict]:
        key = GESTURE_ALIASES.get(gesture_type.lower())
        if not key:
            log.error(
                f"Unknown gesture '{gesture_type}'. Valid: {', '.join(GESTURE_ALIASES)}"
            )
            return None
        gtype = GESTURE_TYPES[key]
        state = self._get_touch_gesture(key)
        if not state or action not in state.get("supported", ()):
            log.error(
                f"{gtype['name']}: action {action} is unavailable for FreeBuds 5i"
            )
            return None
        if "global" in state:
            if side not in (0, SIDE_LEFT):
                return None
            side = 0
        elif {1: "left", 2: "right"}.get(side) not in state:
            return None
        return self._set_touch_gesture(key, side, action)

    def get_long_press_action(self) -> Optional[dict]:
        return self._get_touch_gesture("long_press")

    def set_long_press_action(self, side: int, action: int) -> Optional[dict]:
        return self.set_gesture_action("long_press", side, action)

    def get_triple_click_action(self) -> Optional[dict]:
        return self._get_touch_gesture("triple_click")

    def set_triple_click_action(self, side: int, action: int) -> Optional[dict]:
        return self.set_gesture_action("triple_click", side, action)

    def get_slide_action(self) -> Optional[dict]:
        return self._get_touch_gesture("slide")

    def set_slide_action(self, side: int, action: int) -> Optional[dict]:
        return self.set_gesture_action("slide", side, action)

    def get_double_click_action(self) -> Optional[dict]:
        return self._get_touch_gesture("double_click")

    def set_double_click_action(self, side: int, action: int) -> Optional[dict]:
        return self.set_gesture_action("double_click", side, action)

    def set_noise_control_gesture(self, gesture_type: str, side: int) -> Optional[dict]:
        key = GESTURE_ALIASES.get(gesture_type.lower())
        if not key:
            log.error(
                f"Unknown gesture '{gesture_type}'. Valid: {', '.join(GESTURE_ALIASES)}"
            )
            return None
        nc_action = ACTION_NOISE_CONTROL.get(key)
        if nc_action is None:
            log.error(f"{GESTURE_TYPES[key]['name']} has no noise-control action")
            return None
        return self.set_gesture_action(key, side, nc_action)

    def get_noise_control_status(self) -> dict:
        result = {"noise_control_assigned": [], "details": {}}
        for gkey, gtype in GESTURE_TYPES.items():
            resp = self._get_touch_gesture(gkey)
            result["details"][gkey] = resp
            nc_action = ACTION_NOISE_CONTROL.get(gkey)
            if resp and nc_action is not None:
                for side_key in ("left", "right"):
                    if resp.get(side_key) == nc_action:
                        result["noise_control_assigned"].append(
                            {
                                "gesture": gkey,
                                "gesture_name": gtype["name"],
                                "side": SIDE_LEFT if side_key == "left" else SIDE_RIGHT,
                                "side_name": "Left" if side_key == "left" else "Right",
                            }
                        )
        nc = result["noise_control_assigned"]
        if nc:
            log.debug(f"Noise control assigned to {len(nc)} gesture(s):")
            for g in nc:
                log.debug(f"  {g['gesture_name']} ({g['side_name']})")
        else:
            log.debug("No gesture currently assigned to noise control")
        return result

    def get_feature(self, feat: str) -> Optional[dict]:
        entry = FEATURES.get(feat)
        if not entry:
            log.error(f"Unknown feature '{feat}'. Valid: {', '.join(FEATURES)}")
            return None
        return getattr(self, entry["get"])()

    def set_feature(self, feat: str, enable: bool) -> Optional[dict]:
        entry = FEATURES.get(feat)
        if not entry:
            log.error(f"Unknown feature '{feat}'. Valid: {', '.join(FEATURES)}")
            return None
        setter = entry.get("set")
        if not setter:
            log.error(f"{entry['name']} is read-only")
            return None
        result = getattr(self, setter)(enable)
        if result and result.get("success") is None:
            result["success"] = (self.get_feature(feat) or {}).get("enabled") is enable
        return result

    def start_pair(self) -> Optional[dict]:
        frames = self.send_command(Cmd.STATE_PAIR)
        f = self._match_frame(frames, 0x2B, 0x90)
        if not f:
            log.warning("No pair-state set response")
            return None
        data = f["data"]
        result = {"raw": data.hex()}
        status = self._parse_status_code(data)
        if status is not None:
            result["success"] = status == 100000
            result["status"] = status
            if result["success"]:
                log.debug("Pair state: entering pairing")
            else:
                log.warning(f"Pair state: set failed (status=0x{status:08X})")
        else:
            result["success"] = True
            log.debug("Pair state: entering pairing")
        return result

    def _parse_uint_get(
        self, frames: list[dict], svc: int, cmd: int, name: str
    ) -> Optional[dict]:

        f = self._match_frame(frames, svc, cmd)
        if not f:
            log.warning(f"No {name} response")
            return None
        data = f["data"]
        result = {"raw": data.hex()}
        status = self._parse_status_code(data)
        if status is not None:
            result["status"] = status
            result["status_ok"] = status == 100000
            if result["status_ok"]:
                log.debug(f"{name}: status OK")
            else:
                log.debug(f"{name}: status=0x{status:08X}")
            return result
        val = self._extract_tlv_value(data, 1)
        if val is not None:
            result["value"] = int.from_bytes(val, "big")
            log.debug(f"{name}: value={result['value']}")
            return result
        b = self._extract_byte_at(data, 2)
        if b is not None:
            result["value"] = b
            log.debug(f"{name}: value={b}")
            return result
        log.warning(f"{name}: unrecognized response (data={data.hex()})")
        return result

    def get_game_low_latency(self) -> Optional[dict]:
        return self._parse_bool_get(
            self.send_command(Cmd.GET_GAME_LOW_LATENCY),
            0x2B,
            0x6C,
            0x6C,
            "Game low latency",
        )

    def set_game_low_latency(self, enable: bool) -> Optional[dict]:
        return self._send_bool_setter(
            Cmd.set_game_low_latency(enable), 0x2B, 0x6C, "Game low latency", enable
        )

    def get_dual_connect(self) -> Optional[dict]:
        return self._parse_bool_get(
            self.send_command(Cmd.GET_DUAL_CONNECT), 0x2B, 0x2F, 0x2E, "Dual connect"
        )

    def set_dual_connect(self, enable: bool) -> Optional[dict]:
        return self._send_bool_setter(
            Cmd.set_dual_connect(enable), 0x2B, 0x2E, "Dual connect", enable
        )

    def get_translate_mode(self) -> Optional[dict]:
        return self._parse_bool_get(
            self.send_command(Cmd.GET_TRANSLATE_MODE),
            0x2B,
            0x4D,
            0x4C,
            "Translate mode",
        )

    def set_translate_mode(self, enable: bool) -> Optional[dict]:
        return self._send_bool_setter(
            Cmd.set_translate_mode(enable), 0x2B, 0x4C, "Translate mode", enable
        )

    def get_voice_enhance(self) -> Optional[dict]:
        return self._parse_bool_get(
            self.send_command(Cmd.GET_VOICE_ENHANCE), 0x2B, 0x42, 0x41, "Voice enhance"
        )

    def set_voice_enhance(self, enable: bool) -> Optional[dict]:
        return self._send_bool_setter(
            Cmd.set_voice_enhance(enable), 0x2B, 0x41, "Voice enhance", enable
        )

    def get_32k_hd(self) -> Optional[dict]:
        return self._parse_bool_get(
            self.send_command(Cmd.GET_32K_HD), 0x2B, 0x46, 0x45, "32K HD voice"
        )

    def set_32k_hd(self, enable: bool) -> Optional[dict]:
        return self._send_bool_setter(
            Cmd.set_32k_hd(enable), 0x2B, 0x45, "32K HD voice", enable
        )

    def get_hd_switch(self) -> Optional[dict]:
        frame = self._match_frame(self.send_command(Cmd.GET_HD_SWITCH), 0x2B, 0xA3)
        if frame:
            value = self._extract_tlv_value(frame["data"], 2)
            if value in (b"\x00", b"\x01"):
                return {"enabled": value == b"\x01"}
        return None

    def set_hd_switch(self, enable: bool) -> Optional[dict]:
        return self._send_bool_setter(
            Cmd.set_hd_switch(enable), 0x2B, 0xA2, "Prioritize sound quality", enable
        )

    def locator(self, side, ring=None):
        if side not in ("left", "right"):
            raise ValueError("Choose left or right")
        index = int(side == "right")
        if ring is not None:
            if ring and (self.get_wearing_status() or {}).get(side + "_ear") != 0:
                return {"success": False, "error": "Remove the earbud before ringing it"}
            cmd = bytes((0x2B, 0x5D, 1, 2, index, int(not ring)))
            frame = self._match_frame(self.send_command(cmd), 0x2B, 0x5D)
            if frame and self._parse_status_code(frame["data"]) not in (None, 100000):
                return {"success": False, "status": self._parse_status_code(frame["data"])}
        cmd = bytes((0x2B, 0x5E, 1, 1, index))
        frame = self._match_frame(self.send_command(cmd), 0x2B, 0x5E)
        value = self._extract_tlv_value(frame["data"], 2) if frame else None
        if value is None or len(value) != 2 or value[0] != index or value[1] not in (0, 1):
            return None
        ringing = value[1] == 0
        return {"ringing": ringing, "success": ring is None or ringing == ring}

    def get_left_right_ear(self) -> Optional[dict]:
        return self._parse_bool_get(
            self.send_command(Cmd.GET_LEFT_RIGHT_EAR),
            0x2B,
            0x9A,
            0x99,
            "L/R ear recognition",
        )

    def set_left_right_ear(self, enable: bool) -> Optional[dict]:
        return self._send_bool_setter(
            Cmd.set_left_right_ear(enable), 0x2B, 0x99, "L/R ear recognition", enable
        )

    def get_wind_mode(self) -> Optional[dict]:
        return self._parse_bool_get(
            self.send_command(Cmd.GET_WIND_MODE), 0x2B, 0x95, 0x94, "Wind mode"
        )

    def set_wind_mode(self, enable: bool) -> Optional[dict]:
        return self._send_bool_setter(
            Cmd.set_wind_mode(enable), 0x2B, 0x94, "Wind mode", enable
        )

    def get_silent_upgrade(self) -> Optional[dict]:
        return self._parse_bool_get(
            self.send_command(Cmd.GET_SILENT_UPGRADE),
            0x2B,
            0x70,
            0x6F,
            "Silent upgrade",
        )

    def set_silent_upgrade(self, enable: bool) -> Optional[dict]:
        return self._send_bool_setter(
            Cmd.set_silent_upgrade(enable), 0x2B, 0x6F, "Silent upgrade", enable
        )

    def get_health_alerts(self) -> Optional[dict]:
        return self._parse_bool_get(
            self.send_command(Cmd.GET_HEALTH_ALERTS), 0x2B, 0x61, 0x60, "Health alerts"
        )

    def set_health_alerts(self, enable: bool) -> Optional[dict]:
        return self._send_bool_setter(
            Cmd.set_health_alerts(enable), 0x2B, 0x60, "Health alerts", enable
        )

    def get_wearing_status(self) -> Optional[dict]:
        frames = self.send_command(Cmd.GET_WEARING_STATUS)
        f = self._match_frame(frames, 0x2B, 0x25)
        if not f:
            log.warning("No wearing status response")
            return None
        data = f["data"]
        result = {"raw": data.hex()}
        status = self._parse_status_code(data)
        if status is not None:
            result["status"] = status
            result["status_ok"] = status == 100000
            log.debug(f"Wearing status: status=0x{status:08X}")
            return result
        for tlv in parse_tlv(data):
            v = tlv["value"]
            if tlv["tag"] == 1 and len(v) == 1:
                result["left_ear"] = v[0]
                result["left_in"] = v[0] == 1
            elif tlv["tag"] == 2 and len(v) == 1:
                result["right_ear"] = v[0]
                result["right_in"] = v[0] == 1
        log.debug(f"Wearing status: {result}")
        return result

    def get_dormant_time(self) -> Optional[dict]:
        return self._parse_uint_get(
            self.send_command(Cmd.GET_DORMANT_TIME), 0x2B, 0x48, "Dormant time"
        )

    def set_dormant_time(self, option: int, seconds: int) -> Optional[dict]:
        frames = self.send_command(Cmd.set_dormant_time(option, seconds))
        f = self._match_frame(frames, 0x2B, 0x47)
        if not f:
            log.warning("No dormant time set response")
            return None
        data = f["data"]
        result = {"option": option, "seconds": seconds}
        status = self._parse_status_code(data)
        if status is not None:
            result["success"] = status == 100000
            result["status"] = status
            if result["success"]:
                log.debug(f"Dormant time: set to {seconds}s")
            else:
                log.warning(f"Dormant time: set failed (status=0x{status:08X})")
        else:
            result["success"] = True
            log.debug(f"Dormant time: set to {seconds}s")
        return result

    def get_pair_state(self) -> Optional[dict]:
        return self._parse_uint_get(
            self.send_command(Cmd.QUERY_PAIR), 0x2B, 0x8F, "Pair state"
        )

    def run_fit_test(self) -> dict:
        if not shutil.which("paplay") or not shutil.which("pactl"):
            return {"success": False, "error": "Fit test requires paplay and pactl"}
        if not self._connected or not self.mac_address:
            return {"success": False, "error": "FreeBuds disconnected"}
        sinks = subprocess.check_output(
            ["pactl", "list", "short", "sinks"], text=True, timeout=5
        )
        address = self.mac_address.replace(":", "_").replace("-", "_").lower()
        sink = next(
            (
                fields[1]
                for row in sinks.splitlines()
                if len(fields := row.split()) >= 2
                and address in fields[1].lower()
                and "bluez" in fields[1].lower()
                and "headset" not in fields[1].lower()
            ),
            None,
        )
        if not sink:
            return {"success": False, "error": "FreeBuds playback sink unavailable"}
        audio = fit_audio()
        with self._lock:
            wearing = self.get_wearing_status() or {}
            if not (wearing.get("left_in") and wearing.get("right_in")):
                return {"success": False, "error": "Wear both buds for the fit test"}
            version = self.get_fit_detect_version() or {}
            volume_steps = 15 if version.get("value") == 1 else 8
            player = None
            try:
                frames = self.send_command(Cmd.GET_FIT_CHECK, 0.5)
                ack = self._match_frame(frames, 0x2B, 0x26)
                if not ack or self._extract_tlv_value(ack["data"], 2) != bytes([0]):
                    return {
                        "success": False,
                        "error": "Fit test start was not confirmed",
                    }
                player = subprocess.Popen(
                    [
                        "paplay",
                        "--device",
                        sink,
                        "--volume",
                        str(65536 * volume_steps // 15),
                        str(audio),
                    ]
                )
                received = b""
                parsed_count = 0
                deadline = time.monotonic() + 10
                result = {}
                while True:
                    for frame in frames:
                        if frame["svc"] == 0x2B and frame["cmd"] == 0x27:
                            value = self._extract_tlv_value(frame["data"], 1)
                            if value in (b"\x04", b"\x05"):
                                return {
                                    "success": False,
                                    "error": "Acoustic interference",
                                }
                            if value in (b"\x00", b"\x01", b"\x02", b"\x03"):
                                result["left" if value[0] < 2 else "right"] = (
                                    "good" if value[0] in (0, 2) else "adjust"
                                )
                    playback = player.poll()
                    if playback not in (0, None):
                        return {"success": False, "error": "Test audio playback failed"}
                    if playback == 0 and len(result) == 2:
                        return {"success": True, **result}
                    if time.monotonic() >= deadline:
                        break
                    self.sock.settimeout(0.25)
                    try:
                        chunk = self.sock.recv(4096)
                        if not chunk:
                            break
                        received += chunk
                    except socket.timeout:
                        pass
                    parsed = parse_frames(received)
                    frames = [f for f in parsed[parsed_count:] if f["crc_ok"]]
                    parsed_count = len(parsed)
                return {"success": False, "error": "Incomplete fit report", **result}
            finally:
                try:
                    if player is not None and player.poll() is None:
                        player.terminate()
                        try:
                            player.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            player.kill()
                            player.wait()
                finally:
                    self.exit_fit_check()

    def get_fit_check(self) -> Optional[dict]:
        return self._parse_uint_get(
            self.send_command(Cmd.GET_FIT_CHECK), 0x2B, 0x26, "Earplug fit check"
        )

    def exit_fit_check(self) -> Optional[dict]:
        frames = self.send_command(Cmd.EXIT_FIT_CHECK)
        f = self._match_frame(frames, 0x2B, 0x26)
        if not f:
            log.warning("No fit-check exit response")
            return None
        data = f["data"]
        result = {"raw": data.hex()}
        status = self._parse_status_code(data)
        if status is not None:
            result["success"] = status == 100000
            result["status"] = status
        else:
            result["success"] = self._extract_tlv_value(data, 2) == bytes([2])
        log.debug(f"Fit-check exit: {result}")
        return result

    def get_fit_detect_version(self) -> Optional[dict]:
        return self._parse_uint_get(
            self.send_command(Cmd.GET_FIT_DETECT_VERSION),
            0x2B,
            0x37,
            "Fit-detect version",
        )

    def get_heartbeat(self) -> Optional[dict]:
        return self._parse_uint_get(
            self.send_command(Cmd.HEARTBEAT), 0x2B, 0x4E, "Heartbeat"
        )

    def get_bt_main_status(self) -> Optional[dict]:
        return self._parse_bool_get(
            self.send_command(Cmd.GET_BT_MAIN_STATUS),
            0x2B,
            0x6A,
            0x6A,
            "BT main status",
        )

    def get_close_cover_remind(self) -> Optional[dict]:
        return self._parse_bool_get(
            self.send_command(Cmd.GET_CLOSE_COVER_REMIND),
            0x2B,
            0x7F,
            0x7F,
            "Close-cover remind",
        )

    def get_music_mode(self) -> Optional[dict]:
        return self._parse_uint_get(
            self.send_command(Cmd.GET_MUSIC_MODE), 0x2B, 0x53, "Music mode"
        )

    def get_ambient_sound(self) -> Optional[dict]:
        return self._parse_bool_get(
            self.send_command(Cmd.GET_AMBIENT_SOUND), 0x2B, 0x2C, 0x2C, "Ambient sound"
        )

    def get_connect_ability(self) -> Optional[dict]:
        return self._parse_uint_get(
            self.send_command(Cmd.GET_CONNECT_ABILITY), 0x2B, 0x2D, "Connect ability",
        )

    def _parse_bonded_device(self, data: bytes) -> dict:
        dev = {}
        for tlv in parse_tlv(data):
            v = tlv["value"]
            tag = tlv["tag"]
            if tag == 2 and len(v) == 1:
                dev["number"] = v[0]
            elif tag == 3 and len(v) == 1:
                dev["index"] = v[0]
            elif tag == 4 and len(v) == 6:
                dev["addr"] = mac_to_str(v)
                dev["byte_addr"] = v
            elif tag == 5 and len(v) == 1:
                dev["conn_state"] = v[0] & 1
                dev["business_state"] = (v[0] & 0x0E) >> 1
                dev["in_business"] = ((v[0] & 0x0E) >> 1) > 1
            elif tag == 6 and len(v) == 1:
                dev["type"] = v[0]
            elif tag == 7 and len(v) == 1:
                dev["primary"] = v[0]
            elif tag == 8 and len(v) == 1:
                dev["back_conn_permit"] = v[0]
            elif tag == 9 and v:
                dev["name"] = v.decode("utf-8", errors="ignore").strip().rstrip("\x00")
            elif tag == 10 and len(v) == 1:
                dev["allow_audio_auto_switch"] = v[0] == 1
            elif tag == 11 and len(v) == 1:
                dev["nearlink"] = v[0] == 1
            elif tag in (13, 15) and len(v) == 1:
                dev["lock_channel"] = v[0] == 1
        return dev

    def _parse_device_report(self, data: bytes) -> dict:
        rep = {}
        for tlv in parse_tlv(data):
            v = tlv["value"]
            tag = tlv["tag"]
            rep["type"] = tag
            if tag == 1:
                rep["indices"] = [b for b in v if b != 0xFF]
            elif tag == 2 and len(v) == 6:
                rep["addr"] = mac_to_str(v)
            elif tag == 3 and len(v) == 1:
                rep["flag"] = v[0] == 1
            elif tag == 4 and len(v) == 6:
                rep["byte_addr"] = v
                rep["addr"] = mac_to_str(v)
            elif tag == 5 and len(v) == 7:
                rep["addr"] = mac_to_str(v[:6])
                rep["conn_state"] = v[6] & 1
                rep["business_state"] = (v[6] & 0x0E) >> 1
                rep["in_business"] = ((v[6] & 0x0E) >> 1) > 1
            elif tag == 6 and len(v) == 7:
                rep["addr"] = mac_to_str(v[:6])
                rep["back_conn_permit"] = v[6]
            elif tag == 7 and len(v) == 6:
                rep["addr"] = mac_to_str(v)
            elif tag == 8 and len(v) == 7:
                rep["addr"] = mac_to_str(v[:6])
                rep["allow_audio_auto_switch"] = v[6] == 1
            elif tag == 9 and len(v) == 7:
                rep["addr"] = mac_to_str(v[:6])
                rep["lock_channel"] = v[6] == 1
        return rep

    def get_bonded_devices(self, timeout: float = 2.0) -> list[dict]:
        frames = self.send_command(Cmd.GET_DEVICES_BONDED, timeout)
        devices = {}
        for f in frames:
            if f["svc"] != 0x2B:
                continue
            if f["cmd"] == 0x31:
                dev = self._parse_bonded_device(f["data"])
                if dev.get("addr"):
                    devices[dev["addr"]] = dev
            elif f["cmd"] == 0x36:
                rep = self._parse_device_report(f["data"])
                addr = rep.get("addr")
                if not addr or addr not in devices:
                    continue
                dev = devices[addr]
                if rep.get("type") == 5:
                    dev["conn_state"] = rep["conn_state"]
                    dev["business_state"] = rep.get("business_state")
                    dev["in_business"] = rep.get("in_business", False)
                elif rep.get("type") == 6:
                    dev["back_conn_permit"] = rep["back_conn_permit"]
                elif rep.get("type") == 8:
                    dev["allow_audio_auto_switch"] = rep["allow_audio_auto_switch"]
                elif rep.get("type") == 9:
                    dev["lock_channel"] = rep["lock_channel"]
        result = list(devices.values())
        result.sort(key=lambda d: d.get("index", 255))
        log.debug(f"Bonded devices: {len(result)}")
        for d in result:
            log.debug(
                f"  [{d.get('index')}] {d.get('name', '?')} {d.get('addr')} "
                f"state={d.get('conn_state')} primary={d.get('primary')}"
            )
        return result

    def _resolve_bonded_mac(self, target: str, timeout: float = 2.0) -> Optional[str]:
        mac = target.strip().upper().replace("-", ":")
        if re.match(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$", mac):
            return mac
        try:
            index = int(target)
        except ValueError:
            log.warning(f"Device target must be a MAC or index, got '{target}'")
            return None
        for d in self.get_bonded_devices(timeout):
            if d.get("index") == index:
                return d["addr"]
        log.warning(f"No bonded device with index {index}")
        return None

    def _parse_type_operate_result(self, data: bytes) -> Optional[dict]:
        result = {}
        for tlv in parse_tlv(data):
            if tlv["tag"] == 30 and len(tlv["value"]) == 1:
                result["type"] = tlv["value"][0]
            elif tlv["tag"] == 31 and len(tlv["value"]) == 1:
                result["result"] = tlv["value"][0]
        if result:
            return result
        status = self._parse_status_code(data)
        if status is not None:
            return {"type": None, "result": status}
        return None

    def _send_single_device_setting(self, sub: int, mac: str) -> Optional[dict]:
        mac_bytes = mac_to_bytes(mac)
        if len(mac_bytes) != 6:
            log.warning(f"Invalid MAC: {mac}")
            return None
        frames = self.send_command(Cmd.single_device_setting(sub, mac_bytes))
        for f in frames:
            if f["svc"] == 0x2B and f["cmd"] == 0x33:
                res = self._parse_type_operate_result(f["data"])
                if res:
                    return {
                        "mac": mac,
                        "sub": sub,
                        **res,
                        "success": res.get("result") in (0, 100000)
                        and res.get("type") in (None, sub),
                    }
        if frames:
            return {"mac": mac, "sub": sub, "type": None, "result": None}
        return None

    def connect_device(self, mac: str) -> Optional[dict]:
        return self._send_single_device_setting(1, mac)

    def disconnect_device(self, mac: str) -> Optional[dict]:
        return self._send_single_device_setting(2, mac)

    def unpair_device(self, mac: str) -> Optional[dict]:
        return self._send_single_device_setting(3, mac)

    def set_device_preference(
        self, mac: str, preference: str, enabled: bool
    ) -> Optional[dict]:
        options = {
            "reconnect": ("back_conn_permit", 4, 5),
            "audio-switch": ("allow_audio_auto_switch", 6, 7),
        }
        if preference not in options or type(enabled) is not bool:
            return None
        field, on, off = options[preference]
        device = next(
            (
                d
                for d in self.get_bonded_devices()
                if d["byte_addr"] == mac_to_bytes(mac)
            ),
            {},
        )
        if field not in device:
            return {
                "success": False,
                "error": "Device does not advertise this preference",
            }
        return self._send_single_device_setting(on if enabled else off, mac)

    def set_primary_device(self, mac: str) -> Optional[dict]:
        mac_bytes = mac_to_bytes(mac)
        if len(mac_bytes) != 6:
            log.warning(f"Invalid MAC: {mac}")
            return None
        frames = self.send_command(Cmd.set_primary_device(mac_bytes))
        if not frames:
            return None
        f = self._match_frame(frames, 0x2B, 0x32)
        if f:
            status = self._parse_status_code(f["data"])
            if status is not None:
                return {"mac": mac, "success": status == 100000, "status": status}
            success = any(
                d["byte_addr"] == mac_bytes and d.get("primary") == 1
                for d in self.get_bonded_devices()
            )
            return {"mac": mac, "success": success}
        return {"mac": mac, "success": None, "raw": frames[0]["data"].hex()}

    def _find_anc_mode(self, data: bytes) -> Optional[int]:
        if self._is_status_response(data):
            return None
        val = self._extract_tlv_value(data, 1)
        if val:
            if len(val) == 1 and val[0] in NC_MODES:
                return val[0]
            if len(val) == 2 and val[1] in NC_MODES:
                return val[1]
            return None
        if parse_tlv(data):
            return None
        b = self._extract_byte_at(data, 2)
        if b is not None and b in NC_MODES:
            return b
        return None

    def get_anc_state(self) -> Optional[dict]:
        frames = self.send_command(Cmd.GET_ANC_STATE)
        f = self._match_frame(frames, 0x2B, 0x05)
        if not f:
            log.warning("No ANC state response")
            return None
        data = f["data"]
        result = {"raw": data.hex(), "source": "anc_state"}
        status = self._parse_status_code(data)
        if status is not None:
            result["status"] = status
            result["status_ok"] = status in (0, 100000)
            if result["status_ok"]:
                log.debug("ANC state: status OK")
            else:
                log.debug(f"ANC state: status=0x{status:08X}")
            return result
        mode = self._find_anc_mode(data)
        if mode is not None:
            result["mode"] = mode
            result["mode_name"] = NC_MODES[mode]
            val = self._extract_tlv_value(data, 1)
            if val and len(val) == 2 and mode == NC_MODE_ON:
                level = val[0]
                result["level"] = level
                result["level_name"] = NC_LEVELS.get(level, f"Unknown ({level})")
            log.debug(f"ANC state: {NC_MODES[mode]}")
            return result
        log.warning(f"ANC state: unrecognized response (data={data.hex()})")
        return result

    def get_anc_mode_level(self) -> Optional[dict]:
        frames = self.send_command(Cmd.GET_ANC_MODE_LEVEL)
        f = self._match_frame(frames, 0x2B, 0x07)
        if not f:
            log.warning("No ANC mode+level response")
            return None
        data = f["data"]
        result = {"raw": data.hex(), "source": "anc_mode_level"}
        for tlv in parse_tlv(data):
            v = tlv["value"]
            if tlv["tag"] == 1 and len(v) == 1:
                result["mode"] = v[0]
                result["mode_name"] = NC_MODES.get(v[0], f"Unknown ({v[0]})")
            elif tlv["tag"] == 2 and len(v) == 1:
                result["common_index"] = v[0]
                result["level_name"] = NC_LEVELS.get(v[0], f"Unknown ({v[0]})")
            elif tlv["tag"] == 3 and len(v) == 1:
                result["plane_index"] = v[0]
            elif tlv["tag"] == 4 and len(v) == 1:
                result["fly_mode"] = v[0]
            elif tlv["tag"] == 5 and len(v) == 2:
                result["mode_scene"] = v[0]
                result["mode_voice"] = v[1] & 0x03
                result["mode_noise"] = (v[1] & 0x3C) >> 2
        if "mode" in result:
            log.debug(
                f"ANC mode+level: mode={result['mode_name']} "
                f"common={result.get('common_index')} plane={result.get('plane_index')}"
            )
        return result

    def get_dynamic_anc_support(self) -> Optional[dict]:
        reply = self._match_frame(
            self.send_command(bytes.fromhex("2b2b0300")), 0x2B, 0x2B
        )
        if reply:
            value = self._extract_tlv_value(reply["data"], 1)
            if value in (bytes([0]), bytes([1])):
                return {"supported": bool(value[0])}
        return None

    def query_noise_reduction_mode(self) -> Optional[dict]:
        frames = self.send_command(Cmd.QUERY_NOISE_REDUCTION_MODE)
        f = self._match_frame(frames, 0x2B, 0x2A)
        if not f:
            log.warning("No noise reduction mode response")
            return None
        data = f["data"]
        result = {"raw": data.hex(), "source": "query_nr_mode"}
        for tlv in parse_tlv(data):
            v = tlv["value"]
            if tlv["tag"] == 1 and len(v) == 2:
                result["submode"] = v[0]
                if v[1] == NC_MODE_ON:
                    result["level"] = v[0]
                    result["level_name"] = NC_LEVELS.get(v[0], f"Unknown ({v[0]})")
                if v[1] == NC_MODE_AWARE:
                    result["awareness_name"] = {
                        1: "Voice enhanced",
                        2: "Awareness",
                        4: "Smart awareness",
                    }.get(v[0], "Unknown")
                result["mode"] = v[1]
                result["mode_name"] = NC_MODES.get(v[1], f"Unknown ({v[1]})")
            elif tlv["tag"] == 2 and len(v) == 1:
                result["extra"] = v[0]
        if "mode" in result:
            log.debug(
                f"Noise reduction mode: {result['mode_name']} "
                f"(level={result.get('level')})"
            )
        return result

    def get_noise_control_setting(self) -> Optional[dict]:
        frames = self.send_command(Cmd.GET_NOISE_CONTROL)
        f = self._match_frame(frames, 0x2B, 0x19)
        if not f:
            log.warning("No noise control (2B 19) response")
            return None
        data = f["data"]
        result = {}
        for tlv in parse_tlv(data):
            tag, value = tlv["tag"], tlv["value"]
            if tag in (1, 2) and len(value) == 1:
                side = "left" if tag == 1 else "right"
                result[side] = value[0]
                result[side + "_name"] = NOISE_CYCLES.get(value[0], "Unknown")
            elif tag == 3:
                result["supported"] = list(value)
        return result or None

    def get_noise_mode(self) -> Optional[dict]:
        for method in (
            self.query_noise_reduction_mode,
            self.get_anc_state,
            self.get_anc_mode_level,
        ):
            r = method()
            if r and "mode" in r:
                return r
        return None

    def _parse_anc_status(self, data: bytes) -> Optional[int]:
        status = self._parse_status_code(data)
        if status is not None:
            return status
        val = self._extract_tlv_value(data, 2)
        if val and len(val) == 1:
            return val[0]
        return None

    def _parse_anc_set_result(
        self, frames: list[dict], svc: int, cmd: int, mode: int, name: str
    ) -> Optional[dict]:

        f = self._match_frame(frames, svc, cmd)
        if not f:
            log.warning(f"No {name} set response")
            return None
        data = f["data"]
        result = {"mode": mode, "mode_name": NC_MODES.get(mode, f"Unknown ({mode})")}

        status = self._parse_anc_status(data)
        if status is not None:
            ok = status in (0, 100000)
            result["success"] = ok
            result["status"] = status
            if ok:
                log.debug(f"{name}: set to {NC_MODES.get(mode, mode)}")
            else:
                log.warning(f"{name}: set failed (status=0x{status:08X})")
            return result

        result["success"] = None
        log.warning(f"{name}: unrecognized set response (resp={data.hex()})")
        return result

    def set_anc_state(self, mode: int) -> Optional[dict]:
        if mode not in NC_MODES:
            log.error(f"Invalid ANC mode {mode}. Valid: {list(NC_MODES.keys())}")
            return None
        frames = self.send_command(Cmd.set_anc_state(mode))
        return self._parse_anc_set_result(frames, 0x2B, 0x04, mode, "ANC state")

    def set_anc_state_extended(self, mode: int, level: int = 0xFF) -> Optional[dict]:
        if mode not in NC_MODES:
            log.error(f"Invalid ANC mode {mode}. Valid: {list(NC_MODES.keys())}")
            return None
        if isinstance(level, str):
            level = resolve_anc_level(level)
            if level is None:
                log.error(
                    f"Invalid ANC level. Valid: {', '.join(NC_LEVELS.values())} (0-3)"
                )
                return None
        if mode == NC_MODE_ON and level not in (*NC_LEVELS, 255):
            return None
        if mode == NC_MODE_OFF and level not in (0, 255):
            return None
        if mode == NC_MODE_AWARE and level not in (1, 2, 255):
            return None
        if mode == NC_MODE_ON and level == NC_LEVEL_DYNAMIC:
            if not (self.get_dynamic_anc_support() or {}).get("supported"):
                return None
        frames = self.send_command(Cmd.set_anc_state_level(mode, level))
        return self._parse_anc_set_result(frames, 0x2B, 0x04, mode, "ANC state+level")

    def set_anc_level(self, level: int) -> Optional[dict]:
        level = resolve_anc_level(level)
        if level is None:
            log.error(
                f"Invalid ANC level. Valid: {', '.join(NC_LEVELS.values())} (0-3)"
            )
            return None
        return self.set_anc_state_extended(NC_MODE_ON, level)

    def set_noise_control_setting(
        self, mode: Optional[int], value: Optional[int] = None
    ) -> Optional[dict]:
        requested = {
            side: cycle
            for side, cycle in (("left", mode), ("right", value))
            if cycle is not None
        }
        if not requested or any(type(cycle) is not int for cycle in requested.values()):
            return None
        state = self.get_noise_control_setting() or {}
        if any(
            side not in state
            or cycle not in NOISE_CYCLES
            or cycle not in state.get("supported", ())
            for side, cycle in requested.items()
        ):
            return None
        frames = self.send_command(Cmd.set_noise_control(mode, value))
        reply = self._match_frame(frames, 0x2B, 0x18)
        if reply:
            status = self._parse_status_code(reply["data"])
            if status is not None and status != 100000:
                return {"success": False, "status": status}
        observed = self.get_noise_control_setting() or {}
        return {
            **requested,
            "success": all(observed.get(k) == v for k, v in requested.items()),
        }

    def set_noise_mode(self, mode: int) -> Optional[dict]:
        return self.set_anc_state_extended(mode, 0 if mode == NC_MODE_OFF else 255)

    def get_sound_effect(self) -> Optional[dict]:
        frames = self.send_command(Cmd.GET_EQ)
        f = self._match_frame(frames, 0x2B, 0x4A)
        if not f:
            log.warning("No sound effect response")
            return None
        data = f["data"]
        result = {"raw": data.hex(), "source": "eq_query"}
        status = self._parse_status_code(data)
        if status is not None:
            result["status"] = status
            result["status_ok"] = status in (0, 100000)
            if result["status_ok"]:
                log.debug("Sound effect: status OK")
            else:
                log.debug(f"Sound effect: status=0x{status:08X}")
            return result
        for tlv in parse_tlv(data):
            v = tlv["value"]
            if tlv["tag"] == 1 and len(v) == 1:
                result["support"] = v[0] == 1
            elif tlv["tag"] == 2 and len(v) == 1:
                result["mode"] = v[0]
                result["mode_name"] = EQ_MODES.get(v[0], f"Unknown ({v[0]})")
            elif tlv["tag"] == 3:
                modes = [b for b in v if b != 0xFF]
                result["modes"] = modes
                result["mode_names"] = [
                    EQ_MODES.get(m, f"Unknown ({m})") for m in modes
                ]
            elif tlv["tag"] == 4 and len(v) == 1:
                result["recommended"] = v[0]
            elif tlv["tag"] == 8:
                result["custom_data"] = v.hex()
        if "mode" in result:
            log.debug(f"Sound effect: {result['mode_name']}")
        return result

    def set_sound_effect(self, mode) -> Optional[dict]:
        mode = resolve_eq_mode(mode)
        if mode is None:
            log.error(
                f"Invalid sound effect. Valid: {', '.join(EQ_MODES.values())} (1|2|3|9)"
            )
            return None
        state = self.get_sound_effect() or {}
        if "modes" in state and mode not in state["modes"]:
            return {"success": False, "error": "EQ preset was not advertised"}
        frames = self.send_command(Cmd.set_eq(mode))
        f = self._match_frame(frames, 0x2B, 0x49)
        if not f:
            log.warning("No sound effect set response")
            return None
        data = f["data"]
        result = {"mode": mode, "mode_name": EQ_MODES[mode]}

        status = self._parse_status_code(data)
        if status is not None:
            ok = status in (0, 100000)
            result["success"] = ok
            result["status"] = status
            if ok:
                log.debug(f"Sound effect: set to {EQ_MODES[mode]}")
            else:
                log.warning(f"Sound effect: set failed (status=0x{status:08X})")
            return result

        result["success"] = None
        log.warning(f"Sound effect: unrecognized set response (resp={data.hex()})")
        return result

    def get_language_setting(self) -> Optional[dict]:
        frames = self.send_command(Cmd.GET_LANGUAGE)
        f = self._match_frame(frames, 0x0C, 0x02)
        if not f:
            log.warning("No language setting response")
            return None

        data = f["data"]
        result = {}
        tlvs = parse_tlv(data)
        for tlv in tlvs:
            tag = tlv["tag"]
            try:
                val = (
                    tlv["value"].decode("utf-8", errors="ignore").strip().rstrip("\x00")
                )
            except Exception:
                val = ""
            if tag == 1:
                if val:
                    result["current"] = val
            elif tag == 2 and len(tlv["value"]) == 1:
                result["unit"] = tlv["value"][0]
            elif tag == 3:
                if val:
                    result["tag3"] = val
                    result["supported"] = [lang.strip() for lang in val.split(",")]
            elif val:
                result[f"tag{tag}"] = val

        log.debug(f"Language setting: {result}")
        return result

    def set_language(self, lang_str: str) -> Optional[dict]:
        supported = (self.get_language_setting() or {}).get("supported")
        if supported and lang_str not in supported:
            return {
                "success": False,
                "error": "Unsupported prompt language",
                "supported": supported,
            }

        frames = self.send_command(Cmd.set_language(lang_str))
        f = self._match_frame(frames, 0x0C, 0x01)
        if not f:
            log.warning("No language set response")
            return None

        data = f["data"]
        result = {"language": lang_str}
        if supported:
            result["supported"] = supported

        status = self._parse_status_code(data)
        if status is not None:
            result["success"] = status == 100000
            result["status"] = status
            if result["success"]:
                log.debug(f"Language set: {lang_str}")
                if supported and lang_str not in supported:
                    log.warning(
                        f"Device said OK but '{lang_str}' not in supported list {supported}"
                    )
            else:
                log.warning(f"Language set failed: status=0x{status:08X} ({status})")
        else:
            result["success"] = None
            log.debug(f"Language set unconfirmed: {data.hex()}")

        return result

    def get_cloud_version(self) -> Optional[dict]:
        frames = self.send_command(Cmd.CLOUD_VERSION)
        f = self._match_frame(frames, 0x09, 0x08)
        if not f:
            log.warning("No cloud version response")
            return None
        result = {"data": f["data"].hex()}
        log.info(f"Cloud version response: {result['data']}")
        return result

    def get_ota_params(self) -> Optional[dict]:
        frames = self.send_command(Cmd.GET_OTA_PARAMS)
        f = self._match_frame(frames, 0x09, 0x02)
        if not f:
            log.warning("No OTA params response")
            return None
        result = {"data": f["data"].hex()}
        log.info(f"OTA params response: {result['data']}")
        return result

    def _try_command(
        self, cmd: bytes, label: str = "", read_timeout: float = 0.5
    ) -> Optional[dict]:
        frames = self.send_command(cmd, read_timeout=read_timeout)
        if not frames:
            return None
        for f in frames:
            if f.get("data"):
                return {"label": label, "cmd": cmd.hex(), "response": f["data"].hex()}
        return {"label": label, "cmd": cmd.hex(), "response": "ack_only"}

    def discover_anc(self, timeout: float = 0.3) -> list:
        results = []
        total = 0
        for svc in [0x01, 0x2B, 0x2C, 0x1B, 0x0B, 0x0D, 0x1C, 0x2D]:
            cmd_max = 40 if svc in (0x01, 0x2B) else 16
            for cmd in range(0, cmd_max):
                if svc == 0x2B and cmd in (14, 15, 16, 17, 22, 23, 28, 29, 30, 31, 32, 33, 34, 35):  # fmt: skip
                    continue
                if svc == 0x01 and cmd in (1, 2, 3, 7, 8, 13, 17, 19, 29, 31, 32):
                    continue
                total += 1
                payload = bytes([svc, cmd, 0x01, 0x00])
                r = self._try_command(
                    payload, f"GET svc={svc:02X} cmd={cmd:02X}", read_timeout=timeout
                )
                if r:
                    results.append(r)
                    log.info(
                        f"Response on svc={svc:02X} cmd={cmd:02X}: {r['response']}"
                    )
        for label, cmd in [
            ("ServiceAbility", Cmd.GET_SERVICE_ABILITY),
            ("CommandAbility", Cmd.GET_COMMAND_ABILITY),
        ]:
            r = self._try_command(cmd, label, read_timeout=timeout)
            if r:
                results.append(r)
        log.info(f"Scan complete: {total} probes, {len(results)} responses")
        return results

    def get_all_info(self) -> dict:
        info = {}
        info["battery"] = self.get_battery()
        info["version"] = self.get_version()
        info["noise_control"] = self.get_noise_control_status()
        info.update(info["noise_control"]["details"])
        info["noise_cycle"] = self.get_noise_control_setting()
        info["anc"] = self.get_noise_mode()
        info["sound_effect"] = self.get_sound_effect()
        info["language"] = self.get_language_setting()
        for fkey in FEATURES:
            info[fkey] = self.get_feature(fkey)
        return info


def scan_freebuds(scan_time: int = 10) -> list[dict]:
    found = []

    try:
        import asyncio
        from bleak import BleakScanner

        log.debug(f"BLE scanning {scan_time}s...")

        def cb(device, adv):
            name = adv.local_name or device.name or ""
            if "orange" in name.lower() or "freebuds" in name.lower():
                log.info(f"  BLE: {name} [{device.address}]")
                entry = {"name": name, "address": device.address, "rssi": adv.rssi}
                if entry not in found:
                    found.append(entry)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        scanner = BleakScanner(cb)
        loop.run_until_complete(scanner.start())
        loop.run_until_complete(asyncio.sleep(scan_time))
        loop.run_until_complete(scanner.stop())
        loop.close()
    except ImportError:
        pass
    except Exception as e:
        log.debug(f"BLE error: {e}")

    try:
        subprocess.run(
            ["bluetoothctl", "--timeout", str(scan_time), "scan", "on"],
            capture_output=True,
            timeout=scan_time + 5,
        )
        result = subprocess.run(
            ["bluetoothctl", "devices"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.strip().split("\n"):
            if "Device" in line:
                parts = line.split(" ", 2)
                if len(parts) >= 3:
                    addr, name = parts[1], parts[2]
                    if name and (
                        "FreeBuds" in name
                        or "freebuds" in name.lower()
                        or "Orange" == name
                    ):
                        log.debug(f"  BT: {name} [{addr}]")
                        entry = {"name": name, "address": addr}
                        if entry not in found:
                            found.append(entry)
    except Exception as e:
        log.debug(f"BT error: {e}")

    return found


def is_paired(address: str) -> bool:
    try:
        r = subprocess.run(
            ["bluetoothctl", "info", address], capture_output=True, text=True, timeout=5
        )
        return "Paired: yes" in r.stdout
    except Exception:
        return False


MAC_FILE = ".mac"


def save_mac(mac: str, path: str = MAC_FILE):
    mac = mac.upper().replace("-", ":")
    with open(path, "w") as f:
        f.write(mac + "\n")
    log.debug(f"Saved MAC {mac} to {path}")
    print(f"Saved MAC {mac} to {path}")


def load_mac(path: str = MAC_FILE) -> Optional[str]:
    try:
        with open(path) as f:
            mac = f.readline().strip()
            if mac:
                mac = mac.upper().replace("-", ":")
                if re.match(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$", mac):
                    log.debug(f"Loaded MAC from {path}: {mac}")
                    return mac
                else:
                    log.warning(f"Invalid MAC format in {path}: {mac}")
            return None
    except FileNotFoundError:
        return None
    except Exception as e:
        log.debug(f"Failed to load MAC from {path}: {e}")
        return None


def resolve_address(args) -> Optional[str]:
    if args.address:
        return args.address

    mac = load_mac()
    if mac:
        args.address = mac
        return mac

    print("Scanning for FreeBuds...")
    devs = scan_freebuds(8)
    if devs:
        mac = devs[0]["address"]
        args.address = mac
        print(f"Found: {mac}")
        try:
            save_mac(mac)
        except Exception:
            pass
        return mac

    print("No FreeBuds found. Use --address or create a .mac file.")
    return None


def cmd_scan(args):
    print("\nScanner\n")
    devices = scan_freebuds(args.time)
    if devices:
        print(f"\nFound {len(devices)}:\n")
        for i, d in enumerate(devices):
            print(f"  [{i}] {d['name']}")
            print(f"      Address: {d['address']}")
            print(f"      Paired:  {is_paired(d['address'])}")
            if "rssi" in d:
                print(f"      RSSI: {d['rssi']}")
            print()
        if args.save:
            with open(args.save, "w") as f:
                json.dump(devices, f, indent=2)
    else:
        print("No FreeBuds found. Ensure they're in pairing mode.\n")
    return devices


def print_run_help():
    # fmt: off
    print("Available commands:")
    print("  bat                            - Get battery levels")
    print("  ver                            - Get firmware/device version")
    print("  info                           - Fetch all settings at once")
    print("  gesture <type> [<side> <act>]  - Get/set gesture (lp|slide|dc|triple|nc)")
    print("  fit                            - Run the ear-tip fit test with Huawei test audio")
    print("  cycle [left|right <1-4>]       - Get/set long-press noise cycle")
    print("  anc [<mode>|level <name|0-3>]  - Get/set noise control (off|on|aware; level: general|cozy|ultra|dynamic)")
    print("  sfx [<name>]                   - Get/set sound effect (default|bass|treble|voices)")
    print("  lang [<code>]                  - Get/set language")
    print("  misc [<name> [on|off]]         - Get/set misc features")
    print("  devices [<action> [<mac|idx>]] - List/connect/disconnect/unpair devices stored on the buds")
    print("  find <left|right> [ring|stop]   - Locate an earbud")
    print("  raw <hex>                      - Send raw command bytes")
    # fmt: on


def print_devices_help():
    # fmt: off
    print("Paired device management (list stored on the buds):")
    print("  devices                       - List all devices")
    print("  devices connect <mac|idx>     - Connect the buds to a device")
    print("  devices disconnect <mac|idx>  - Disconnect from a device")
    print("  devices unpair <mac|idx>      - Forget a device on the buds")
    print("  devices reconnect <mac|idx> on|off   - Allow automatic reconnection")
    print("  devices audio-switch <mac|idx> on|off - Allow automatic audio switching when supported")
    print("  devices primary <mac|idx>     - Set the default/primary device")
    # fmt: on


def print_misc_help():
    print("Misc settings:")
    for key, entry in FEATURES.items():
        usage = " [on|off]" if "set" in entry else ""
        print(f"  misc {key}{usage} - {entry['name']}")


def print_gesture_help():
    print("gesture <type> [<side 1|2> <action>]")
    print("gesture <dc|lp> call <0=enabled|255=disabled>")
    print("gesture slide both <action>")
    print("gesture nc [<type> <side>]")
    for key, entry in GESTURE_TYPES.items():
        print(f"  {key} ({', '.join(entry['aliases'])})")
    print("Read a gesture to list the actions advertised by the buds.")


def run_gesture(ctrl, sub):
    if not sub or sub[0].lower() in ("help", "-h"):
        print_gesture_help()
        return
    gtype = sub[0].lower()
    if gtype == "nc":
        run_nc(ctrl, sub[1:])
        return

    key = GESTURE_ALIASES.get(gtype)
    if not key:
        print(
            f"Unknown gesture '{gtype}'. Use: lp, slide, dc, triple, nc"
        )
        return

    glabel = GESTURE_TYPES[key]["name"]
    rest = sub[1:]
    if len(rest) == 0:
        r = ctrl.get_gesture_action(key)
        if r and "status" in r:
            print_status(glabel, r["status"])
        elif r:
            if "call_action" in r:
                print(
                    f"In-call: {r['call_name']} (choices {r.get('call_supported', [])})"
                )
            if "global" in r:
                print(f"{glabel}: both={r['global_name']}")
            lv = r.get("left")
            rv = r.get("right")
            if lv is not None or rv is not None:
                lstr = (
                    f"Left={r.get('left_name', '?')}"
                    if lv is not None
                    else "Left=unset"
                )
                rstr = (
                    f"Right={r.get('right_name', '?')}"
                    if rv is not None
                    else "Right=unset"
                )
                print(f"{glabel}: {lstr}, {rstr}")
            if "supported" in r:
                print(f"{glabel}: supported: {', '.join(r['supported_names'])}")
            elif lv is None and rv is None and "global" not in r:
                print(f"{glabel}: {r}")
        else:
            print("no response")
    elif len(rest) == 2:
        try:
            scope = rest[0].lower()
            side = 0 if scope in ("both", "call") else int(scope)
            action = int(rest[1])
        except ValueError:
            print(f"Usage: gesture {gtype} <side(1|2)> <action>")
            return
        if side not in (0, 1, 2):
            print("Invalid side")
            return
        if scope == "call":
            r = ctrl.set_call_gesture(key, action)
        else:
            r = ctrl.set_gesture_action(key, side, action)
        if r and r.get("success"):
            act_name = r["action_name"]
            side_name = r["side_name"]
            print(f"{glabel}: {side_name} -> {act_name}")
        elif r and "status" in r:
            print(f"{glabel}: set failed (status=0x{r['status']:08X})")
        elif r:
            print(f"{glabel}: set failed ({r})")
        else:
            print("no response")
    else:
        print(f"Usage: gesture {gtype} [<side(1|2)> <action>]")


def run_nc(ctrl, sub):
    if not sub:
        st = ctrl.get_noise_control_status()
        assigned = st.get("noise_control_assigned", [])
        if assigned:
            print("Noise control assigned to:")
            for g in assigned:
                print(f"  {g['gesture_name']} ({g['side_name']})")
        else:
            print("No gesture set to noise control. Use: gesture nc <gesture> <side>")
        return
    if len(sub) != 2:
        print("Usage: gesture nc <gesture> <side>")
        return

    key = GESTURE_ALIASES.get(sub[0].lower())
    if not key:
        print("Unknown gesture. Use: lp, slide, dc, triple")
        return
    if ACTION_NOISE_CONTROL.get(key) is None:
        print(f"{GESTURE_TYPES[key]['name']} has no noise-control action")
        return
    try:
        side = int(sub[1])
    except ValueError:
        print("Usage: gesture nc <gesture> <side>")
        return
    if side not in (1, 2):
        print("Side must be 1 (left) or 2 (right)")
        return
    r = ctrl.set_noise_control_gesture(key, side)
    if r and r.get("success"):
        side_name = "Left" if side == 1 else "Right"
        gt_name = GESTURE_TYPES[key]["name"]
        print(f"{gt_name} ({side_name}) -> Noise control")
    elif r and "status" in r:
        print(f"Set failed (status=0x{r['status']:08X})")
    elif r:
        print(f"Set failed: {r}")
    else:
        print("No response")


def cmd_run(args):
    if not args.commands:
        print_run_help()
        return
    if not resolve_address(args):
        return

    ctrl = FreeBudsController(args.address)
    if not ctrl.connect():
        return

    i = 0
    while i < len(args.commands):
        parts = args.commands[i].split()
        if not parts:
            i += 1
            continue
        cmd_name = parts[0].lower()

        j = i + 1
        while j < len(args.commands):
            nxt = args.commands[j].split()
            gesture_argument = (
                cmd_name == "gesture"
                and (len(parts) == 1 or (len(parts) == 2 and parts[1] == "nc"))
                and nxt
                and (nxt[0].lower() in GESTURE_ALIASES or nxt[0].lower() == "nc")
            )
            if not nxt or (
                nxt[0].lower() in _CMD_NAMES
                and not gesture_argument
                and not (parts == ["misc"] and nxt[0] == "fit")
            ):
                break
            parts += nxt
            j += 1
        i = j

        try:
            if cmd_name == "gesture":
                run_gesture(ctrl, parts[1:])
            elif cmd_name in GESTURE_ALIASES:
                run_gesture(ctrl, parts)
            elif cmd_name == "help":
                print_run_help()
            elif cmd_name == "fit":
                print(ctrl.run_fit_test() if len(parts) == 1 else "Usage: fit")
            elif cmd_name == "cycle":
                if len(parts) == 1:
                    print(ctrl.get_noise_control_setting() or "No response")
                    for cycle, label in NOISE_CYCLES.items():
                        print(f"  {cycle}  {label}")
                elif len(parts) == 3 and parts[1] in ("left", "right"):
                    cycle = int(parts[2])
                    print(
                        ctrl.set_noise_control_setting(
                            cycle if parts[1] == "left" else None,
                            cycle if parts[1] == "right" else None,
                        )
                        or "Unsupported cycle or no response"
                    )
                else:
                    print("Usage: cycle [left|right <1-4>]")

            elif cmd_name == "find":
                if len(parts) not in (2, 3) or parts[1] not in ("left", "right") or (
                    len(parts) == 3 and parts[2] not in ("ring", "stop")
                ):
                    print("Usage: find <left|right> [ring|stop]")
                else:
                    ring = parts[2] == "ring" if len(parts) == 3 else None
                    result = ctrl.locator(parts[1], ring)
                    if result and result.get("success"):
                        print(f"{parts[1]}: {'ringing' if result['ringing'] else 'silent'}")
                    else:
                        print((result or {}).get("error", "Locator request unconfirmed"))

            elif cmd_name == "bat":
                b = ctrl.get_battery()
                if b:
                    labels = []
                    for side in ("left", "right", "box"):
                        level = b.get(side + "_battery")
                        display = f"{level}%" if level is not None and level <= 100 else "unknown"
                        charging = " (charging)" if b.get(side + "_charging") else ""
                        labels.append(f"{side.title()}: {display}{charging}")
                    print("  ".join(labels))
                else:
                    print("no response")

            elif cmd_name == "ver":
                v = ctrl.get_version()
                if v:
                    for k, val in v.items():
                        print(f"{k}: {val}")
                else:
                    print("no response")

            elif cmd_name == "info":
                info = ctrl.get_all_info()
                for k, v in info.items():
                    if v:
                        if isinstance(v, dict):
                            if "status" in v and not any(
                                kk in v
                                for kk in ("enabled", "value", "mode", "left", "right")
                            ):
                                print_status(k, v["status"])
                                continue
                            items = []
                            for vk, vv in v.items():
                                if isinstance(vv, bool):
                                    items.append(f"{vk}={'On' if vv else 'Off'}")
                                elif isinstance(vv, int) and vk in ("status",):
                                    items.append(f"{vk}=0x{vv:08X}")
                                else:
                                    items.append(f"{vk}={vv}")
                            print(f"{k}: {', '.join(items)}")
                        else:
                            print(f"{k}: {v}")
                    else:
                        print(f"{k}: (no response)")

            elif cmd_name in ("anc", "nc"):
                args_tokens = parts[1:]
                if args_tokens and args_tokens[0].lower() == "level":
                    if len(args_tokens) < 2:
                        print("Usage: anc level <general|cozy|ultra|dynamic> (or 0-3)")
                    else:
                        level = resolve_anc_level(args_tokens[1])
                        if level is None:
                            print(
                                "Unknown ANC level. Use: general|cozy|ultra|dynamic "
                                "(or 0-3)"
                            )
                        else:
                            r = ctrl.set_anc_level(level)
                            if r and r.get("success"):
                                print(f"ANC level: set to {NC_LEVELS[level]}")
                            elif r:
                                print(f"ANC level: set failed ({r})")
                            else:
                                print("no response")
                elif args_tokens:
                    mode = NC_MODE_ALIASES.get(args_tokens[0].lower())
                    if mode is None:
                        print(
                            f"Unknown mode '{args_tokens[0]}'. Use: off|on|aware (or 0|1|2)"
                        )
                    else:
                        r = ctrl.set_noise_mode(mode)
                        if r and r.get("success"):
                            print(f"Noise control: {NC_MODES[mode]}")
                        elif r:
                            print(f"Noise control: set failed ({r})")
                        else:
                            print("no response")
                else:
                    r = ctrl.get_noise_mode()
                    if r and "mode" in r:
                        detail = r.get("level_name") or r.get("awareness_name")
                        suffix = f" ({detail})" if detail and detail != r["mode_name"] else ""
                        print(f"Noise control: {r['mode_name']}{suffix}")
                    elif r:
                        print(
                            f"Noise control: raw={r.get('raw', '?')} "
                            "(unrecognized format, try 'anc off|on|aware')"
                        )
                    else:
                        print(
                            "No response. Device may not support direct ANC mode "
                            "control; try 'gesture nc' to assign noise control to a gesture."
                        )

            elif cmd_name == "sfx":
                if len(parts) >= 2:
                    mode = resolve_eq_mode(parts[1])
                    if mode is None:
                        print(
                            f"Unknown sound effect '{parts[1]}'. Use: default|bass|treble|voices (or 1|2|3|9)"
                        )
                    else:
                        r = ctrl.set_sound_effect(mode)
                        if r and r.get("success"):
                            print(f"Sound effect: {EQ_MODES[mode]}")
                        elif r:
                            print(f"Sound effect: set failed ({r})")
                        else:
                            print("no response")
                else:
                    r = ctrl.get_sound_effect()
                    if r and "mode" in r:
                        print(f"Sound effect: {r['mode_name']}")
                    elif r:
                        print(f"Sound effect: {r}")
                    else:
                        print("no response")

            elif cmd_name == "misc":
                if len(parts) < 2:
                    print_misc_help()
                    continue
                fname = parts[1].lower()
                if fname in ("help", "-h"):
                    print_misc_help()
                elif fname == "fit" and len(parts) == 2:
                    print(ctrl.run_fit_test())
                elif fname == "fit" and len(parts) >= 3 and parts[2].lower() == "exit":
                    r = ctrl.exit_fit_check()
                    if r and r.get("success"):
                        print("Fit check: exited")
                    elif r:
                        print(f"Fit check: exit failed ({r})")
                    else:
                        print("no response")
                elif len(parts) >= 3 and parts[2].lower() in (
                    "on",
                    "1",
                    "true",
                    "yes",
                    "off",
                    "0",
                    "false",
                    "no",
                ):
                    enable = parts[2].lower() in ("on", "1", "true", "yes")
                    r = ctrl.set_feature(fname, enable)
                    if r is None and fname not in FEATURES:
                        print(f"Unknown feature '{fname}'. Use: misc help")
                    elif r and r.get("success"):
                        print(f"{FEATURES[fname]['name']}: {'On' if enable else 'Off'}")
                    elif r and "status" in r:
                        print(
                            f"{FEATURES[fname]['name']}: set failed (status=0x{r['status']:08X})"
                        )
                    elif r:
                        print(f"{FEATURES[fname]['name']}: set failed ({r})")
                    else:
                        print("no response")
                else:
                    r = ctrl.get_feature(fname)
                    if r is None and fname not in FEATURES:
                        print(f"Unknown feature '{fname}'. Use: misc help")
                    elif r and "enabled" in r:
                        print(
                            f"{FEATURES[fname]['name']}: {'On' if r['enabled'] else 'Off'}"
                        )
                    elif r and "value" in r:
                        print(f"{FEATURES[fname]['name']}: {r['value']}")
                    elif r and "status" in r:
                        print_status(FEATURES[fname]["name"], r["status"])
                    elif r:
                        items = []
                        for vk, vv in r.items():
                            if isinstance(vv, bool):
                                items.append(f"{vk}={'On' if vv else 'Off'}")
                            elif vk == "status":
                                items.append(f"{vk}=0x{vv:08X}")
                            else:
                                items.append(f"{vk}={vv}")
                        print(f"{FEATURES[fname]['name']}: {', '.join(items)}")
                    else:
                        print("no response")

            elif cmd_name in ("devices", "dev"):
                action = parts[1].lower() if len(parts) >= 2 else "list"
                if action in ("help", "-h"):
                    print_devices_help()
                elif (
                    action == "list"
                    and i < len(args.commands)
                    and args.commands[i].strip().lower() == "help"
                ):
                    i += 1
                    print_devices_help()
                elif action == "list":
                    devs = ctrl.get_bonded_devices()
                    if not devs:
                        print("No paired devices reported")
                    for d in devs:
                        state = "Connected" if d.get("conn_state") else "Idle"
                        prim = " Primary" if d.get("primary") else ""
                        print(
                            f"[{d.get('index')}] {d.get('name', '?')} "
                            f"{d.get('addr', '?')} - {state}{prim}"
                        )
                elif len(parts) >= 3:
                    if action not in (
                        "connect",
                        "disconnect",
                        "unpair",
                        "primary",
                        "reconnect",
                        "audio-switch",
                    ):
                        print(f"Unknown devices action '{parts[1]}'. Use: devices help")
                    else:
                        mac = ctrl._resolve_bonded_mac(parts[2])
                        if not mac:
                            print(f"Unknown device '{parts[2]}'")
                        elif action in ("reconnect", "audio-switch"):
                            if len(parts) == 4 and parts[3] in ("on", "off"):
                                print(
                                    ctrl.set_device_preference(
                                        mac, action, parts[3] == "on"
                                    )
                                )
                            else:
                                print(f"Usage: devices {action} <mac|idx> on|off")
                        elif action == "connect":
                            r = ctrl.connect_device(mac)
                            if r and r.get("success"):
                                print(f"Connected {mac}")
                            elif r:
                                print(f"Connect failed: result={r.get('result')}")
                            else:
                                print("no response")
                        elif action == "disconnect":
                            r = ctrl.disconnect_device(mac)
                            if r and r.get("success"):
                                print(f"Disconnected {mac}")
                            elif r:
                                print(f"Disconnect failed: result={r.get('result')}")
                            else:
                                print("no response")
                        elif action == "unpair":
                            r = ctrl.unpair_device(mac)
                            if r and r.get("success"):
                                print(f"Unpaired {mac}")
                            elif r:
                                print(f"Unpair failed: result={r.get('result')}")
                            else:
                                print("no response")
                        elif action == "primary":
                            r = ctrl.set_primary_device(mac)
                            if r and r.get("success"):
                                print(f"Primary device: {mac}")
                            elif r:
                                print(f"Set primary failed: raw={r.get('raw', '?')}")
                            else:
                                print("no response")
                else:
                    print(f"Usage: devices {action} <mac|idx>")

            elif cmd_name == "lang":
                if len(parts) >= 2:
                    lang_code = parts[1]
                    r = ctrl.set_language(lang_code)
                    if r:
                        if r.get("success"):
                            print(f"Language set to {lang_code}")
                        else:
                            print(
                                f"Language set failed: status=0x{r.get('status', 0):08X}"
                            )
                            lang_info = ctrl.get_language_setting()
                            if lang_info:
                                support = lang_info.get("tag3", "")
                                if support and lang_code not in support:
                                    print(f"Available languages: {support}")
                                    print(f"Try one of: {support}")
                    else:
                        print("no response")
                else:
                    r = ctrl.get_language_setting()
                    if r:
                        langs = r.get("supported")
                        if langs:
                            print(f"Available: {', '.join(langs)}")
                        else:
                            print(f"Available: {r.get('tag3', '')}")
                    else:
                        print("no response")

            elif cmd_name == "raw" and len(parts) >= 2:
                try:
                    b = bytes.fromhex("".join(parts[1:]))
                    frames = ctrl.send_command(
                        b, args.timeout if hasattr(args, "timeout") else 2.0
                    )
                    for f in frames:
                        print(
                            f"svc=0x{f['svc']:02X} cmd=0x{f['cmd']:02X} data={f['data'].hex()}"
                        )
                except ValueError as e:
                    print(f"Error: {e}")

            else:
                if cmd_name in ("lp", "sp", "slide", "dc", "nc"):
                    print(
                        f"Unknown: {cmd_name} (gesture commands moved under 'gesture' - try: gesture {cmd_name})"
                    )
                else:
                    print(f"Unknown: {cmd_name}")

        except Exception as e:
            print(f"Error: {e}")

        if i < len(args.commands):
            print()

    ctrl.disconnect()


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--debug", action="store_true")

    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("scan", help="Scan for FreeBuds")
    p.add_argument("-t", "--time", type=int, default=10)
    p.add_argument("--save")

    p = sub.add_parser("run", help="Run commands against a FreeBuds device")
    p.add_argument("-a", "--address")
    p.add_argument(
        "commands",
        nargs="*",
        help="Commands to run (e.g. 'bat' 'lang' 'misc wear on' 'anc off')",
    )
    p.add_argument("-t", "--timeout", type=float, default=2.0)

    args = parser.parse_args()
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "run":
        cmd_run(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
