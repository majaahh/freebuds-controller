#!/usr/bin/env python3
# Copyright (c) 2026 Majaahh
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import json
import socket
import subprocess
import logging
import re
from threading import Lock
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
    VERSION = bytes([0x01, 0x07] + sum([[i, 0x00] for i in range(1, 13)], []))
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
    def set_noise_control(mode: int, value: int = None) -> bytes:
        payload = bytes([0x2B, 0x18, 0x01, 0x01, mode & 0xFF])
        if value is not None:
            payload += bytes([0x02, 0x01, value & 0xFF])
        return payload

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

    GET_HD_SWITCH = bytes([0x2B, 0x5E, 0x01, 0x01, 0x01])

    @staticmethod
    def set_hd_switch(enable: bool) -> bytes:
        v = 0x01 if enable else 0x00
        return bytes([0x2B, 0x5D, 0x01, 0x02, v, v])

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
    3: "Noise cancelling on/off",
    4: "Play/Next",
    5: "Noise cancelling on/off/ambient",
    6: "Noise cancelling on/ambient",
    7: "Previous track",
    8: "Play/Previous",
    9: "Noise cancelling off/ambient",
    255: "None",
}

LP_ACTIONS = {
    0: "Voice assistant",
    1: "Play/Pause",
    2: "Next track",
    3: "Noise cancelling on/off",
    4: "Play/Next",
    5: "Noise cancelling on/off/ambient",
    6: "Noise cancelling on/ambient",
    7: "Previous track",
    8: "Play/Previous",
    9: "Noise cancelling off/ambient",
    10: "Noise control",
    11: "Reject call",
    14: "Song recognition",
    15: "Freestyle listen",
    17: "Health query",
    255: "None",
}

TRIPLE_ACTIONS = {
    0: "Voice assistant",
    1: "Play/Pause",
    2: "Next track",
    3: "Noise cancelling on/off",
    4: "Noise control",
    7: "Previous track",
    255: "None",
}

SLIDE_ACTIONS = {
    0: "Volume",
    1: "Prev/Next track",
    255: "None",
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
    "double_click": 5,
    "triple_click": 4,
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
    "help", "bat", "ver", "info",
    "gesture", "anc", "nc", "sfx", "lang", "raw", "misc",
    "lp", "sp", "slide", "dc", "triple", "pinch", "lhold",
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
    "pinch": {
        "name": "Pinch",
        "aliases": ("pinch", "sp"),
        "get": Cmd.GET_PINCH,
        "set": Cmd.set_pinch,
        "svc": 0x2B,
        "cmd": 0x21,
        "set_cmd": 0x20,
        "actions": PINCH_ACTIONS,
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
    "light_hold": {
        "name": "Light hold",
        "aliases": ("lhold", "lh"),
        "get": Cmd.GET_LIGHT_HOLD,
        "set": Cmd.set_light_hold,
        "svc": 0x2B,
        "cmd": 0x93,
        "set_cmd": 0x92,
        "actions": LP_ACTIONS,
    },
}

GESTURE_ALIASES = {}
for _gkey, _gtype in GESTURE_TYPES.items():
    GESTURE_ALIASES[_gkey] = _gkey
    for _alias in _gtype["aliases"]:
        GESTURE_ALIASES[_alias] = _gkey

FEATURES = {
    "greet": {
        "name": "Voice prompts",
        "get": "get_greet_setting",
        "set": "set_greet",
    },
    "wear": {
        "name": "Wear detection",
        "get": "get_wear_setting",
        "set": "set_wear",
    },
    "ivol": {
        "name": "Intellect volume",
        "get": "get_intellect_volume",
        "set": "set_intellect_volume",
    },
    "save": {
        "name": "Saving mode",
        "get": "get_saving_mode",
        "set": "set_saving_mode",
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
    "trans": {
        "name": "Translate mode",
        "get": "get_translate_mode",
        "set": "set_translate_mode",
    },
    "venh": {
        "name": "Voice enhance",
        "get": "get_voice_enhance",
        "set": "set_voice_enhance",
    },
    "32k": {
        "name": "32K HD voice",
        "get": "get_32k_hd",
        "set": "set_32k_hd",
    },
    "hd": {
        "name": "HD sound switch",
        "get": "get_hd_switch",
        "set": "set_hd_switch",
    },
    "lre": {
        "name": "L/R ear recognition",
        "get": "get_left_right_ear",
        "set": "set_left_right_ear",
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
    "wearst": {"name": "Wearing status", "get": "get_wearing_status"},
    "dormant": {"name": "Dormant time", "get": "get_dormant_time"},
    "pair": {"name": "Pair state", "get": "get_pair_state"},
    "fit": {"name": "Earplug fit check", "get": "get_fit_check"},
    "fitver": {"name": "Fit-detect version", "get": "get_fit_detect_version"},
    "hb": {"name": "Heartbeat", "get": "get_heartbeat"},
    "btmain": {"name": "BT main status", "get": "get_bt_main_status"},
    "cover": {"name": "Close-cover remind", "get": "get_close_cover_remind"},
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


class FreeBudsController:
    def __init__(self, mac_address: str = None):
        self.mac_address = mac_address
        self.sock = None
        self._connected = False
        self._lock = Lock()

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

                return parse_frames(response)

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
                result["supported"] = [b for b in v if b != 0xFF]
                result["supported_names"] = [
                    actions.get(b, f"Unknown ({b})") for b in result["supported"]
                ]
                found = True
            elif tlv["tag"] == 4 and len(v) == 1:
                result["call_left"] = v[0]
                result["call_left_name"] = actions.get(v[0], f"Unknown ({v[0]})")
                found = True
            elif tlv["tag"] == 5 and len(v) == 1:
                result["call_right"] = v[0]
                result["call_right_name"] = actions.get(v[0], f"Unknown ({v[0]})")
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
        if not f and frames:
            f = frames[0]
        if not f:
            log.warning(f"No {name} set response")
            return None

        data = f["data"]
        side_name = "Left" if side == SIDE_LEFT else "Right"
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
            if tlv["tag"] in (3, 6) and len(tlv["value"]) == 1:
                code = tlv["value"][0]
                ok = code in (0, 2)
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

        resp_action = self._extract_byte_at(data, 2)
        if resp_action is not None:
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

        success = True
        result = {"enabled": enable, "success": success}
        log.info(f"{name}: set to {'On' if enable else 'Off'}")
        return result

    def _get_touch_gesture(self, key: str) -> Optional[dict]:
        gtype = GESTURE_TYPES[key]
        return self._parse_touch_get(
            self.send_command(gtype["get"]),
            gtype["svc"],
            gtype["cmd"],
            gtype["name"],
            gtype["actions"],
        )

    def _set_touch_gesture(self, key: str, side: int, action: int) -> Optional[dict]:
        gtype = GESTURE_TYPES[key]
        left = action if side == SIDE_LEFT else None
        right = action if side == SIDE_RIGHT else None
        payload = gtype["set"](left, right)
        return self._send_touch_set(
            payload,
            gtype["svc"],
            gtype["set_cmd"],
            gtype["name"],
            side,
            action,
            gtype["actions"],
        )

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
        if action not in gtype["actions"] and action != 255:
            log.warning(
                f"Action {action} not in {gtype['name']} table: "
                f"{list(gtype['actions'])}"
            )
        return self._set_touch_gesture(key, side, action)

    def get_long_press_action(self) -> Optional[dict]:
        return self._get_touch_gesture("long_press")

    def set_long_press_action(self, side: int, action: int) -> Optional[dict]:
        return self._set_touch_gesture("long_press", side, action)

    def get_short_press_action(self) -> Optional[dict]:
        return self._get_touch_gesture("pinch")

    def set_short_press_action(self, side: int, action: int) -> Optional[dict]:
        return self._set_touch_gesture("pinch", side, action)

    def get_pinch_action(self) -> Optional[dict]:
        return self._get_touch_gesture("pinch")

    def set_pinch_action(self, side: int, action: int) -> Optional[dict]:
        return self._set_touch_gesture("pinch", side, action)

    def get_triple_click_action(self) -> Optional[dict]:
        return self._get_touch_gesture("triple_click")

    def set_triple_click_action(self, side: int, action: int) -> Optional[dict]:
        return self._set_touch_gesture("triple_click", side, action)

    def get_light_hold_action(self) -> Optional[dict]:
        return self._get_touch_gesture("light_hold")

    def set_light_hold_action(self, side: int, action: int) -> Optional[dict]:
        return self._set_touch_gesture("light_hold", side, action)

    def get_slide_action(self) -> Optional[dict]:
        return self._get_touch_gesture("slide")

    def set_slide_action(self, side: int, action: int) -> Optional[dict]:
        return self._set_touch_gesture("slide", side, action)

    def get_double_click_action(self) -> Optional[dict]:
        return self._get_touch_gesture("double_click")

    def set_double_click_action(self, side: int, action: int) -> Optional[dict]:
        return self._set_touch_gesture("double_click", side, action)

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
        return self._set_touch_gesture(key, side, nc_action)

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
        return getattr(self, setter)(enable)

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
        return self._parse_bool_get(
            self.send_command(Cmd.GET_HD_SWITCH), 0x2B, 0x5E, 0x5D, "HD sound switch"
        )

    def set_hd_switch(self, enable: bool) -> Optional[dict]:
        return self._send_bool_setter(
            Cmd.set_hd_switch(enable), 0x2B, 0x5D, "HD sound switch", enable
        )

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
            result["success"] = True
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
        return self._parse_bool_get(
            self.send_command(Cmd.GET_CONNECT_ABILITY),
            0x2B,
            0x2D,
            0x2D,
            "Connect ability",
        )

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
            if val and len(val) == 2:
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
                result["level"] = v[0]
                result["level_name"] = NC_LEVELS.get(v[0], f"Unknown ({v[0]})")
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
        result = {"raw": data.hex(), "source": "noise_control_lr"}
        for tlv in parse_tlv(data):
            v = tlv["value"]
            if tlv["tag"] == 1 and len(v) == 1:
                result["left"] = v[0]
                result["left_name"] = NC_MODES.get(v[0], f"Unknown ({v[0]})")
            elif tlv["tag"] == 2 and len(v) == 1:
                result["right"] = v[0]
                result["right_name"] = NC_MODES.get(v[0], f"Unknown ({v[0]})")
        log.debug(f"Noise control L/R: {result}")
        return result

    def get_noise_mode(self) -> Optional[dict]:
        for method in (
            self.get_anc_state,
            self.query_noise_reduction_mode,
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
        if not f and frames:
            f = frames[0]
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
        frames = self.send_command(Cmd.set_anc_state_level(mode, level))
        return self._parse_anc_set_result(frames, 0x2B, 0x04, mode, "ANC state+level")

    def set_anc_level(self, level: int) -> Optional[dict]:
        level = resolve_anc_level(level)
        if level is None:
            log.error(
                f"Invalid ANC level. Valid: {', '.join(NC_LEVELS.values())} (0-3)"
            )
            return None
        frames = self.send_command(Cmd.set_anc_level(level))
        f = self._match_frame(frames, 0x2B, 0x08)
        if not f:
            log.warning("No ANC level set response")
            return None
        data = f["data"]
        result = {"level": level, "level_name": NC_LEVELS[level]}

        status = self._parse_anc_status(data)
        if status is not None:
            ok = status in (0, 100000)
            result["success"] = ok
            result["status"] = status
            if ok:
                log.debug(f"ANC level: set to {NC_LEVELS[level]}")
            else:
                log.warning(f"ANC level: set failed (status=0x{status:08X})")
        else:
            result["success"] = None
            log.warning(f"ANC level: unrecognized response (resp={data.hex()})")
        return result

    def set_noise_control_setting(self, mode: int, value: int = None) -> Optional[dict]:
        frames = self.send_command(Cmd.set_noise_control(mode, value))
        f = self._match_frame(frames, 0x2B, 0x18)
        if not f:
            log.warning("No noise control (2B 18) set response")
            return None
        data = f["data"]
        result = {"mode": mode}

        status = self._parse_anc_status(data)
        if status is not None:
            ok = status in (0, 100000)
            result["success"] = ok
            result["status"] = status
            if ok:
                log.debug(f"Noise control: set mode={mode}")
            else:
                log.warning(f"Noise control: set failed (status=0x{status:08X})")
        else:
            result["success"] = None
            log.warning(f"Noise control: unrecognized response (resp={data.hex()})")
        return result

    def set_noise_mode(self, mode: int) -> Optional[dict]:
        r = self.set_anc_state(mode)
        if r is not None:
            if r.get("success"):
                return r
            log.debug("Simple ANC set not confirmed, trying mode+level form...")
            r2 = self.set_anc_state_extended(
                mode, 0x00 if mode == NC_MODE_OFF else 0xFF
            )
            if r2 is not None and r2.get("success"):
                return r2
        return r

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
        supported = None
        try:
            lang_info = self.get_language_setting()
            if lang_info and "supported" in lang_info:
                supported = lang_info["supported"]
                if lang_str not in supported:
                    log.warning(f"'{lang_str}' not in supported languages: {supported}")
        except Exception:
            pass

        frames = self.send_command(Cmd.set_language(lang_str))
        f = self._match_frame(frames, 0x0C, 0x01)
        if not f:
            for frame in frames:
                if frame["svc"] == 0x0C:
                    f = frame
                    break
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
            result["success"] = True
            log.debug(f"Language set: {lang_str} (raw response: {data.hex()})")

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
        info["long_press"] = self.get_long_press_action()
        info["pinch"] = self.get_pinch_action()
        info["slide"] = self.get_slide_action()
        info["double_click"] = self.get_double_click_action()
        info["triple_click"] = self.get_triple_click_action()
        info["light_hold"] = self.get_light_hold_action()
        info["noise_control"] = self.get_noise_control_status()
        info["anc"] = self.get_noise_mode()
        info["sound_effect"] = self.get_sound_effect()
        info["language"] = self.get_language_setting()
        for fkey, fentry in FEATURES.items():
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
    print("  bat                           - Get battery levels")
    print("  ver                           - Get firmware/device version")
    print("  info                          - Fetch all settings at once")
    print("  gesture <type> [<side> <act>] - Get/set gesture (lp|pinch|slide|dc|triple|lhold|nc)")
    print("  anc [<mode>|level <name|0-3>] - Get/set noise control (off|on|aware; level: general|cozy|ultra|dynamic)")
    print("  sfx [<name>]                  - Get/set sound effect (default|bass|treble|voices)")
    print("  lang [<code>]                 - Get/set language")
    print("  misc [<name> [on|off]]        - Get/set misc features")
    print("  raw <hex>                     - Send raw command bytes")
    # fmt: on


def print_misc_help():
    # fmt: off
    print("Misc settings:")
    print("  misc <name> [on|off] - Get/set")
    print()
    print("  Settable:")
    print("    greet   - Voice prompts")
    print("    wear    - Wear detection")
    print("    ivol    - Intellect volume")
    print("    save    - Saving mode")
    print("    glat    - Game low latency")
    print("    dual    - Dual connect")
    print("    trans   - Translate mode")
    print("    venh    - Voice enhance")
    print("    32k     - 32K HD voice")
    print("    hd      - HD sound switch")
    print("    lre     - L/R ear recognition")
    print("    wind    - Wind mode")
    print("    silent  - Silent upgrade")
    print("    health  - Health alerts")
    print()
    print("  Read-only:")
    print("    wearst  - Wearing status")
    print("    dormant - Dormant time (misc dormant <seconds> sets)")
    print("    pair    - Pair state (misc pair on enters pairing)")
    print("    fit     - Earplug fit check (misc fit exit exits)")
    print("    fitver  - Fit-detect version")
    print("    hb      - Heartbeat")
    print("    btmain  - BT main status")
    print("    cover   - Close-cover remind")
    print("    music   - Music mode")
    print("    ambient - Ambient sound")
    print("    conn    - Connect ability")
    # fmt: on


def print_gesture_help():
    # fmt: off
    print("Gesture commands:")
    print("  gesture <gesture>              - Get gesture action")
    print("  gesture <gesture> <side> <act> - Set gesture action")
    print("  gesture nc                     - Show noise control assignments")
    print("  gesture nc <gesture> <side>    - Assign noise control to a gesture")
    print()
    print("  Side: 1=left, 2=right")
    print("  Gestures: lp (long press), pinch/sp, slide/sl, dc (double click),")
    print("            triple/tri, lhold (light hold)")
    print()
    print("  Common actions: 0=Voice assistant 1=Play/Pause 2=Next 3=NC on/off 7=Previous 255=None")
    print("  Long press extras: 10=Noise control 11=Reject call 14=Song recognition 15=Freestyle listen 17=Health query")
    print("  Double click extras: 4=Play/Next 5=NC on/off/ambient 6=NC on/ambient 8=Play/Previous 9=NC off/ambient")
    print("  Pinch actions: 0=Translate 1=Voice memo 2=Pairing 3=Freestyle 4=Pinch chat 5=Song recognition")
    print("  Slide actions: 0=Volume 1=Prev/Next track")
    print("  Triple click: 0=Assistant 1=Play/Pause 2=Next 3=NC on/off 4=Noise control")
    # fmt: on


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
            f"Unknown gesture '{gtype}'. Use: lp, pinch, slide, dc, triple, lhold, nc"
        )
        return

    glabel = GESTURE_TYPES[key]["name"]
    actions = GESTURE_TYPES[key]["actions"]
    rest = sub[1:]
    if len(rest) == 0:
        r = ctrl.get_gesture_action(key)
        if r and "status" in r:
            print_status(glabel, r["status"])
        elif r:
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
            elif "supported" in r:
                print(f"{glabel}: supported: {', '.join(r['supported_names'])}")
            else:
                print(f"{glabel}: {r}")
        else:
            print("no response")
    elif len(rest) == 2:
        try:
            side = int(rest[0])
            action = int(rest[1])
        except ValueError:
            print(f"Usage: gesture {gtype} <side(1|2)> <action>")
            return
        if side not in (1, 2):
            print("Side must be 1 (left) or 2 (right)")
            return
        r = ctrl.set_gesture_action(key, side, action)
        if r and r.get("success"):
            act_name = actions.get(action, f"action {action}")
            side_name = "Left" if side == 1 else "Right"
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
        print("Unknown gesture. Use: lp, pinch, slide, dc, triple, lhold")
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
            if not nxt or nxt[0].lower() in _CMD_NAMES:
                break
            parts += nxt
            j += 1
        i = j

        if cmd_name == "gesture":
            run_gesture(
                ctrl, parts[1:] or [w for tok in args.commands[i:] for w in tok.split()]
            )
            break
        elif cmd_name in ("lp", "sp", "slide", "dc", "triple", "pinch", "lhold"):
            run_gesture(ctrl, [cmd_name] + parts[1:])
            break

        try:
            if cmd_name == "help":
                print_run_help()

            elif cmd_name == "bat":
                b = ctrl.get_battery()
                if b:
                    print(
                        f"L:{b.get('left_battery', '?')}%  R:{b.get('right_battery', '?')}%  Box:{b.get('box_battery', '?')}%"
                    )
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
                        print(f"Noise control: {r['mode_name']}")
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
                elif fname == "dormant" and len(parts) >= 3:
                    try:
                        seconds = int(parts[2])
                    except ValueError:
                        print("Usage: misc dormant <seconds>")
                        continue
                    r = ctrl.set_dormant_time(0, seconds)
                    if r and r.get("success"):
                        print(f"Dormant time: set to {seconds}s")
                    elif r:
                        print(f"Dormant time: set failed ({r})")
                    else:
                        print("no response")
                elif (
                    fname == "pair"
                    and len(parts) >= 3
                    and parts[2].lower() in ("on", "1", "true", "yes")
                ):
                    r = ctrl.start_pair()
                    if r and r.get("success"):
                        print("Pairing mode: enabled")
                    elif r:
                        print(f"Pairing mode: set failed ({r})")
                    else:
                        print("no response")
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
        help="Commands to run (e.g. 'bat' 'lang' 'greet on' 'anc off')",
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
