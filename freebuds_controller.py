#!/usr/bin/env python3
# Copyright (c) 2026 Majaahh
# SPDX-License-Identifier: GPL-3.0-or-later

# jjh.java — command builders
# AppParseDataHandleHelper.java — response parsing
# ProtocolAPI.java — high-level API
# kph.java — CRC-16 polynomial 0x8005
# LinkDataHandleHelper.java — SPP frame layer

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

# kph.java: CRC-16 polynomial 0x8005
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


# jjh.java command builders
class Cmd:
    # jjh.d() getDeviceBattery
    BATTERY = bytes([0x01, 0x08, 0x01, 0x00, 0x02, 0x00, 0x03, 0x00])
    # jjh.e() getDeviceVersion
    VERSION = bytes([0x01, 0x07] + sum([[i, 0x00] for i in range(1, 13)], []))
    # jjh.c() unknown (svc=0x01, cmd=0x1D)
    CMD_01_1D = bytes([0x01, 0x1D, 0x01, 0x01, 0x01])

    # jjh.a(int,int) setDoubleClickAction
    @staticmethod
    def set_double_click(side: int, action: int) -> bytes:
        return bytes([0x01, 0x1F, side, 0x01, action])

    # jjh.f() getDoubleClickAction
    GET_DOUBLE_CLICK = bytes([0x01, 0x20, 0x03, 0x00])
    # jjh.a() cloudVersion
    CLOUD_VERSION = bytes([0x09, 0x08])
    # jjh.k() getOTAParams
    GET_OTA_PARAMS = bytes([0x09, 0x02, 0x01, 0x00])
    # jjh.a() cancelOTA
    CANCEL_OTA = bytes([0x09, 0x08])
    # jjh.b() checkDeviceOTAState
    CHECK_OTA_STATE = bytes([0x09, 0x01, 0x01, 0x00])
    # jjh.p() language/psi
    LANGUAGE_PSI = bytes([0x0A, 0x0E, 0x02, 0x01, 0x00])
    # jjh.i() getLanguageSetting
    GET_LANGUAGE = bytes([0x0C, 0x02, 0x01, 0x00, 0x02, 0x00, 0x03, 0x00])

    # jjh.a(String) setLanguageSetting
    @staticmethod
    def set_language(lang_str: str) -> bytes:
        lang_bytes = lang_str.encode("us-ascii", errors="ignore")
        return bytes([0x0C, 0x01, 0x01, len(lang_bytes)]) + lang_bytes

    # jjh.g() getGreetSetting
    GET_GREET = bytes([0x2B, 0x0F, 0x01, 0x00])

    # jjh.b(boolean) setGreetEnable
    @staticmethod
    def set_greet(enable: bool) -> bytes:
        return bytes([0x2B, 0x0E, 0x01, 0x01, 0x01 if enable else 0x00])

    # jjh.o() getWearSetting
    GET_WEAR = bytes([0x2B, 0x11, 0x01, 0x00])

    # jjh.e(boolean) setWearEnable
    @staticmethod
    def set_wear(enable: bool) -> bytes:
        return bytes([0x2B, 0x10, 0x01, 0x01, 0x01 if enable else 0x00])

    # jjh.j() getLongPressAction
    GET_LONG_PRESS = bytes([0x2B, 0x17, 0x01, 0x00, 0x02, 0x00, 0x03, 0x00])

    # jjh.b(int,int) setLongPressAction
    @staticmethod
    def set_long_press(side: int, action: int) -> bytes:
        return bytes([0x2B, 0x16, side, 0x01, action])

    # jjh.m() getShortPressAction
    GET_SHORT_PRESS = bytes([0x2B, 0x21, 0x01, 0x00, 0x02, 0x00, 0x03, 0x00])

    # jjh.c(int,int) setShortPressAction
    @staticmethod
    def set_short_press(side: int, action: int) -> bytes:
        return bytes([0x2B, 0x20, side, 0x01, action])

    # jjh.n() getSlideAction
    GET_SLIDE = bytes([0x2B, 0x1F, 0x01, 0x00, 0x02, 0x00, 0x03, 0x00])

    # jjh.d(int,int) setSlideAction
    @staticmethod
    def set_slide(side: int, action: int) -> bytes:
        return bytes([0x2B, 0x1E, side, 0x01, action])

    # jjh.l() getSavingMode
    GET_SAVING_MODE = bytes([0x2B, 0x1D, 0x01, 0x00])

    # jjh.d(boolean) setSavingMode
    @staticmethod
    def set_saving_mode(enable: bool) -> bytes:
        return bytes([0x2B, 0x1C, 0x01, 0x01, 0x01 if enable else 0x00])

    # jjh.h() getIntellectVolume
    GET_INTELLECT_VOLUME = bytes([0x2B, 0x23, 0x01, 0x00])

    # jjh.c(boolean) setIntellectVolume
    @staticmethod
    def set_intellect_volume(enable: bool) -> bytes:
        return bytes([0x2B, 0x22, 0x01, 0x01, 0x01 if enable else 0x00])

    # jjh.q() setTime
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


# LinkDataHandleHelper.java frame layer
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
        total = 4 + (frame_len - 1) + 2  # sync+len+type + payload + crc
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


# AppParseDataHandleHelper.java response handlers
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

        log.info(f"Connecting SPP to {mac} (channel {channel})...")
        try:
            self.sock = socket.socket(
                socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
            )
            self.sock.settimeout(10)
            self.sock.connect((mac, channel))
            self._connected = True
            log.info("Connected")
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
                except:
                    pass
                self.sock = None
            self._connected = False
        log.info("Disconnected")

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

    # AppParseDataHandleHelper.b(): 0x7F 0x04 [4-byte status/error]
    def _is_status_response(self, data: bytes) -> bool:
        return len(data) >= 6 and data[0] == 0x7F and data[1] == 0x04

    def _parse_status_code(self, data: bytes) -> Optional[int]:
        if self._is_status_response(data) and len(data) >= 6:
            return (data[2] << 24) | (data[3] << 16) | (data[4] << 8) | data[5]
        return None

    # jjh.d() battery, AppParseDataHandleHelper$c: TLV tag=2 -> [L%, R%, Box%]
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
            log.info(
                f"Battery: L={bat['left_battery']}% "
                f"R={bat['right_battery']}% Box={bat['box_battery']}%"
            )
            return bat
        log.warning("Battery: no tag=2 found in TLV")
        return None

    # jjh.e() device version, TLV tags: 3=model 7=firmware 9=serial 10=bt
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
                        log.info(f"Firmware: {val}")
            except:
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
                log.info(f"{name}: status OK")
            else:
                log.warning(f"{name}: status=0x{status:08X}")
            return result

        val = self._extract_byte_at(data, 2)
        if val is not None and val in (0, 1):
            result = {"enabled": val == 1}
            log.info(f"{name}: {'ON' if result['enabled'] else 'OFF'}")
            return result

        tlvs = parse_tlv(data)
        for tlv in tlvs:
            if len(tlv["value"]) == 1 and tlv["value"][0] in (0, 1):
                result = {"enabled": tlv["value"][0] == 1}
                log.info(
                    f"{name}: {'ON' if result['enabled'] else 'OFF'} (from TLV tag {tlv['tag']})"
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

    def _parse_gesture_get(
        self, frames: list[dict], svc: int, cmd: int, gesture_name: str
    ) -> Optional[dict]:

        f = self._match_frame(frames, svc, cmd)
        if not f:
            log.warning(f"No {gesture_name} response")
            return None

        data = f["data"]

        status = self._parse_status_code(data)
        if status is not None:
            if status == 100000:
                log.info(f"{gesture_name}: not configured (status=OK, value=100000)")
            else:
                log.info(
                    f"{gesture_name}: status response code={status} (0x{status:08X})"
                )
            return {"status": status, "status_ok": status == 100000, "raw": data.hex()}

        tlvs = parse_tlv(data)
        side = None
        action = None
        for tlv in tlvs:
            if tlv["tag"] == 1 and len(tlv["value"]) >= 1:
                side = tlv["value"][0]
            elif tlv["tag"] == 2 and len(tlv["value"]) >= 1:
                action = tlv["value"][0]

        side_name = None
        result = {}
        if side is not None:
            side_name = (
                "Left"
                if side == SIDE_LEFT
                else ("Right" if side == SIDE_RIGHT else f"Side={side}")
            )
            result["side"] = side
            result["side_name"] = side_name
        if action is not None:
            result["action"] = action
            result["action_name"] = GESTURE_ACTIONS.get(action, f"Unknown ({action})")

        if side is not None or action is not None:
            desc = (
                f"{side_name or '?'} -> {result.get('action_name', '?')}"
                if action is not None
                else f"side={side}, no action set"
            )
            log.info(f"{gesture_name}: {desc}")
            return result

        log.warning(f"{gesture_name}: unrecognized response format (data={data.hex()})")
        return None

    def _send_gesture_set(
        self,
        cmd_payload: bytes,
        svc: int,
        cmd: int,
        gesture_name: str,
        side: int,
        action: int,
    ) -> Optional[dict]:

        frames = self.send_command(cmd_payload)
        f = self._match_frame(frames, svc, cmd)
        if not f:
            log.warning(f"No {gesture_name} set response")
            return None

        data = f["data"]
        side_name = "Left" if side == SIDE_LEFT else "Right"
        action_name = GESTURE_ACTIONS.get(action, f"Unknown ({action})")
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
                log.info(f"{gesture_name}: {side_name} -> {action_name} (status OK)")
            else:
                log.warning(f"{gesture_name}: set failed (status=0x{status:08X})")
            return result

        resp_action = self._extract_byte_at(data, 2)
        result["success"] = resp_action == action if resp_action is not None else None
        if result["success"]:
            log.info(f"{gesture_name}: {side_name} -> {action_name} (set ok)")
        else:
            log.warning(f"{gesture_name}: set may have failed (resp={resp_action})")
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
                log.info(f"{name}: set to {'ON' if enable else 'OFF'} (status OK)")
            else:
                log.warning(f"{name}: set failed (status=0x{status:08X})")
            return result

        val = self._extract_byte_at(data, 2)
        success = True
        result = {"enabled": enable, "success": success}
        log.info(f"{name}: set to {'ON' if enable else 'OFF'}")
        return result

    def get_long_press_action(self) -> Optional[dict]:
        return self._parse_gesture_get(
            self.send_command(Cmd.GET_LONG_PRESS), 0x2B, 0x17, "Long press"
        )

    def set_long_press_action(self, side: int, action: int) -> Optional[dict]:
        return self._send_gesture_set(
            Cmd.set_long_press(side, action), 0x2B, 0x16, "Long press", side, action
        )

    def get_short_press_action(self) -> Optional[dict]:
        return self._parse_gesture_get(
            self.send_command(Cmd.GET_SHORT_PRESS), 0x2B, 0x21, "Short press"
        )

    def set_short_press_action(self, side: int, action: int) -> Optional[dict]:
        return self._send_gesture_set(
            Cmd.set_short_press(side, action), 0x2B, 0x20, "Short press", side, action
        )

    def get_slide_action(self) -> Optional[dict]:
        return self._parse_gesture_get(
            self.send_command(Cmd.GET_SLIDE), 0x2B, 0x1F, "Slide"
        )

    def set_slide_action(self, side: int, action: int) -> Optional[dict]:
        return self._send_gesture_set(
            Cmd.set_slide(side, action), 0x2B, 0x1E, "Slide", side, action
        )

    def get_double_click_action(self) -> Optional[dict]:
        return self._parse_gesture_get(
            self.send_command(Cmd.GET_DOUBLE_CLICK), 0x01, 0x20, "Double click"
        )

    def set_double_click_action(self, side: int, action: int) -> Optional[dict]:
        return self._send_gesture_set(
            Cmd.set_double_click(side, action), 0x01, 0x1F, "Double click", side, action
        )

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
            try:
                val = (
                    tlv["value"].decode("utf-8", errors="ignore").strip().rstrip("\x00")
                )
                if val:
                    result[f"tag{tlv['tag']}"] = val
            except:
                result[f"tag{tlv['tag']}"] = tlv["value"].hex()

        support_raw = result.get("tag3", "")
        if support_raw and "," in support_raw:
            result["supported"] = [l.strip() for l in support_raw.split(",")]

        log.info(f"Language setting: {result}")
        return result

    def set_language(self, lang_str: str) -> Optional[dict]:
        supported = None
        try:
            lang_info = self.get_language_setting()
            if lang_info and "supported" in lang_info:
                supported = lang_info["supported"]
                if lang_str not in supported:
                    log.warning(f"'{lang_str}' not in supported languages: {supported}")
        except:
            pass

        frames = self.send_command(Cmd.set_language(lang_str))
        f = self._match_frame(frames, 0x0C, 0x01)
        if not f:
            for frame in frames:
                if frame["svc"] == 0x0C:
                    f = frame
                    break
        if not f:
            log.warning(f"No language set response")
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
                log.info(f"Language set: {lang_str} (OK)")
                if supported and lang_str not in supported:
                    log.warning(
                        f"Device said OK but '{lang_str}' not in supported list {supported}"
                    )
            else:
                log.warning(f"Language set failed: status=0x{status:08X} ({status})")
        else:
            result["success"] = True
            log.info(f"Language set: {lang_str} (raw response: {data.hex()})")

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

    def get_all_info(self) -> dict:
        info = {}
        info["battery"] = self.get_battery()
        info["version"] = self.get_version()
        info["greet"] = self.get_greet_setting()
        info["wear"] = self.get_wear_setting()
        info["intellect_volume"] = self.get_intellect_volume()
        info["saving_mode"] = self.get_saving_mode()
        info["long_press"] = self.get_long_press_action()
        info["short_press"] = self.get_short_press_action()
        info["slide"] = self.get_slide_action()
        info["double_click"] = self.get_double_click_action()
        info["language"] = self.get_language_setting()
        return info


def scan_freebuds(scan_time: int = 10) -> list[dict]:
    found = []

    try:
        import asyncio
        from bleak import BleakScanner

        log.info(f"BLE scanning {scan_time}s...")

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
                        log.info(f"  BT: {name} [{addr}]")
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
    except:
        return False


MAC_FILE = ".mac"


def save_mac(mac: str, path: str = MAC_FILE):
    mac = mac.upper().replace("-", ":")
    with open(path, "w") as f:
        f.write(mac + "\n")
    log.info(f"Saved MAC {mac} to {path}")
    print(f"Saved MAC {mac} to {path}")


def load_mac(path: str = MAC_FILE) -> Optional[str]:
    try:
        with open(path) as f:
            mac = f.readline().strip()
            if mac:
                mac = mac.upper().replace("-", ":")
                if re.match(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$", mac):
                    log.info(f"Loaded MAC from {path}: {mac}")
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
        except:
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


def cmd_interactive(args):
    if not args.address:
        devs = scan_freebuds(8)
        if not devs:
            print("No FreeBuds found.")
            return
        args.address = devs[0]["address"]

    ctrl = FreeBudsController(args.address)
    if not ctrl.connect():
        return

    print(f"\nFreeBuds Interactive Shell")
    print(f"Connected: {args.address}")
    print("Commands: bat, ver, greet, wear, ivol, save, lp, sp, slide, dc,")
    print("          raw <hex>, lang, info, help, quit\n")

    def bool_str(val):
        return "ON" if val else "OFF"

    def show_bool_result(r, label):
        if not r:
            print(f"  {label}: no response")
        elif "enabled" in r:
            print(f"  {label}: {bool_str(r['enabled'])}")
        elif "status" in r:
            s = r.get("status", 0)
            print(
                f"  {label}: status=0x{s:08X} ({'OK' if r.get('status_ok') else 'FAIL'})"
            )
        elif "raw" in r:
            print(f"  {label}: raw={r['raw']}")

    def show_gesture_result(r, label):
        if not r:
            print(f"  {label}: no response")
        elif "status" in r:
            s = r.get("status", 0)
            print(
                f"  {label}: status=0x{s:08X} ({'OK' if r.get('status_ok') else 'FAIL'})"
            )
        elif "action" in r or "side" in r:
            sn = r.get("side_name", f"side={r.get('side', '?')}")
            an = r.get("action_name", f"action={r.get('action', '?')}")
            print(f"  {label}: {sn} -> {an}")
        elif "raw" in r:
            print(f"  {label}: raw={r['raw']}")

    try:
        while True:
            inp = input("fb> ").strip()
            if not inp:
                continue
            parts = inp.split()
            cmd = parts[0].lower()

            if cmd in ("q", "quit", "exit"):
                break
            elif cmd == "help":
                print("bat                          - Get battery")
                print("ver                          - Get version")
                print("greet [on|off]               - Get/set voice prompts")
                print("wear [on|off]                - Get/set wear detection")
                print("ivol [on|off]                - Get/set intellect volume")
                print("save [on|off]                - Get/set saving mode")
                print("lp                           - Get long press action")
                print("lp <side> <action>           - Set long press (1=left,2=right)")
                print("sp                           - Get short press action")
                print("sp <side> <action>           - Set short press")
                print("slide                        - Get slide action")
                print("slide <side> <action>        - Set slide")
                print("dc                           - Get double click action")
                print("dc <side> <action>           - Set double click")
                print("lang                         - Get language")
                print("lang <code>                  - Set language (e.g. en-US)")
                print("raw <hex>                    - Send raw command")
                print("info                         - Fetch all settings")
                print("help                         - This")
                print("quit                         - Exit")
                print(
                    f"Gesture actions: {', '.join(f'{k}={v}' for k, v in GESTURE_ACTIONS.items())}"
                )
            elif cmd == "bat":
                b = ctrl.get_battery()
                if b:
                    print(
                        f"  L:{b.get('left_battery', '?')}%  R:{b.get('right_battery', '?')}%  Box:{b.get('box_battery', '?')}%"
                    )
            elif cmd == "ver":
                v = ctrl.get_version()
                if v:
                    for k, val in v.items():
                        print(f"  {k}: {val}")
            elif cmd == "info":
                info = ctrl.get_all_info()
                for k, v in info.items():
                    if v:
                        print(f"  {k}: {v}")
                    else:
                        print(f"  {k}: (no response)")
            elif cmd == "greet":
                if len(parts) >= 2:
                    enable = parts[1].lower() in ("on", "1", "true", "yes")
                    r = ctrl.set_greet(enable)
                    if r and r.get("success"):
                        print(f"  Voice prompts: {'ON' if enable else 'OFF'} (set ok)")
                    elif r:
                        print(
                            f"  Voice prompts: set failed (status={r.get('status', '?')})"
                        )
                else:
                    show_bool_result(ctrl.get_greet_setting(), "Voice prompts")
            elif cmd == "wear":
                if len(parts) >= 2:
                    enable = parts[1].lower() in ("on", "1", "true", "yes")
                    r = ctrl.set_wear(enable)
                    if r and r.get("success"):
                        print(f"  Wear detection: {'ON' if enable else 'OFF'} (set ok)")
                    elif r:
                        print(
                            f"  Wear detection: set failed (status={r.get('status', '?')})"
                        )
                else:
                    show_bool_result(ctrl.get_wear_setting(), "Wear detection")
            elif cmd == "ivol":
                if len(parts) >= 2:
                    enable = parts[1].lower() in ("on", "1", "true", "yes")
                    r = ctrl.set_intellect_volume(enable)
                    if r and r.get("success"):
                        print(
                            f"  Intellect volume: {'ON' if enable else 'OFF'} (set ok)"
                        )
                    elif r:
                        print(
                            f"  Intellect volume: set failed (status={r.get('status', '?')})"
                        )
                else:
                    show_bool_result(ctrl.get_intellect_volume(), "Intellect volume")
            elif cmd == "save":
                if len(parts) >= 2:
                    enable = parts[1].lower() in ("on", "1", "true", "yes")
                    r = ctrl.set_saving_mode(enable)
                    if r and r.get("success"):
                        print(f"  Saving mode: {'ON' if enable else 'OFF'} (set ok)")
                    elif r:
                        print(
                            f"  Saving mode: set failed (status={r.get('status', '?')})"
                        )
                else:
                    show_bool_result(ctrl.get_saving_mode(), "Saving mode")
            elif cmd == "lp":
                if len(parts) >= 3:
                    try:
                        side = int(parts[1])
                        action = int(parts[2])
                        r = ctrl.set_long_press_action(side, action)
                        if r and r.get("success"):
                            print(f"  Long press set ok")
                        elif r:
                            print(f"  Long press set failed: {r}")
                    except ValueError:
                        print("  Usage: lp <side(1|2)> <action>")
                else:
                    show_gesture_result(ctrl.get_long_press_action(), "Long press")
            elif cmd == "sp":
                if len(parts) >= 3:
                    try:
                        side = int(parts[1])
                        action = int(parts[2])
                        r = ctrl.set_short_press_action(side, action)
                        if r and r.get("success"):
                            print(f"  Short press set ok")
                        elif r:
                            print(f"  Short press set failed: {r}")
                    except ValueError:
                        print("  Usage: sp <side(1|2)> <action>")
                else:
                    show_gesture_result(ctrl.get_short_press_action(), "Short press")
            elif cmd == "slide":
                if len(parts) >= 3:
                    try:
                        side = int(parts[1])
                        action = int(parts[2])
                        r = ctrl.set_slide_action(side, action)
                        if r and r.get("success"):
                            print(f"  Slide set ok")
                        elif r:
                            print(f"  Slide set failed: {r}")
                    except ValueError:
                        print("  Usage: slide <side(1|2)> <action>")
                else:
                    show_gesture_result(ctrl.get_slide_action(), "Slide")
            elif cmd == "dc":
                if len(parts) >= 3:
                    try:
                        side = int(parts[1])
                        action = int(parts[2])
                        r = ctrl.set_double_click_action(side, action)
                        if r and r.get("success"):
                            print(f"  Double click set ok")
                        elif r:
                            print(f"  Double click set failed: {r}")
                    except ValueError:
                        print("  Usage: dc <side(1|2)> <action>")
                else:
                    show_gesture_result(ctrl.get_double_click_action(), "Double click")
            elif cmd == "lang":
                if len(parts) >= 2:
                    lang_code = parts[1]
                    r = ctrl.set_language(lang_code)
                    if r:
                        if r.get("success"):
                            print(f"  Language set to {lang_code} (OK)")
                            if r.get("supported") and lang_code not in r["supported"]:
                                print(
                                    f"  Note: '{lang_code}' not in supported list: {r['supported']}"
                                )
                        else:
                            print(
                                f"  Language set failed: status=0x{r.get('status', 0):08X}"
                            )
                            if r.get("supported"):
                                print(f"  Supported: {', '.join(r['supported'])}")
                else:
                    r = ctrl.get_language_setting()
                    if r:
                        support = r.get("supported", [])
                        current = r.get("tag1", "not set")
                        print(f"  Current: {current}")
                        print(f"  Supported: {', '.join(support)}")
                        for k, v in r.items():
                            if k not in ("supported",):
                                print(f"  {k}: {v}")
            elif cmd == "raw" and len(parts) >= 2:
                try:
                    b = bytes.fromhex(parts[1].replace(" ", ""))
                    frames = ctrl.send_command(b, args.timeout)
                    for f in frames:
                        print(
                            f"  svc=0x{f['svc']:02X} cmd=0x{f['cmd']:02X} data={f['data'].hex()}"
                        )
                except ValueError as e:
                    print(f"  Error: {e}")
            else:
                print(f"  Unknown: {cmd}")
    except KeyboardInterrupt:
        print()
    finally:
        ctrl.disconnect()


def cmd_run(args):
    if not resolve_address(args):
        return

    ctrl = FreeBudsController(args.address)
    if not ctrl.connect():
        return

    for cmd_str in args.commands:
        parts = cmd_str.split()
        if not parts:
            continue
        cmd_name = parts[0].lower()
        print(f"> {cmd_str}")

        try:
            if cmd_name == "help":
                print("Available commands:")
                print("  bat                   - Get battery levels")
                print("  ver                   - Get firmware/device version")
                print("  info                  - Fetch all settings at once")
                print("  greet [on|off]        - Get/set voice prompts")
                print("  wear [on|off]         - Get/set wear detection")
                print("  ivol [on|off]         - Get/set intellect volume")
                print("  save [on|off]         - Get/set saving mode")
                print("  lp [<side> <act>]     - Get/set long press action")
                print("  sp [<side> <act>]     - Get/set short press action")
                print("  slide [<side> <act>]  - Get/set slide action")
                print("  dc [<side> <act>]     - Get/set double click action")
                print("  lang [<code>]         - Get/set language")
                print("  raw <hex>             - Send raw command bytes")
                print()
                print("Gesture action codes: 0=None 1=Assistant 2=NoiseCtrl")
                print("  3=Prev 4=Next 5=VolUp 6=VolDown 7=Play 8=Answer")
                print("Side: 1=left, 2=right")

            elif cmd_name == "bat":
                b = ctrl.get_battery()
                if b:
                    print(
                        f"  L:{b.get('left_battery', '?')}%  R:{b.get('right_battery', '?')}%  Box:{b.get('box_battery', '?')}%"
                    )
                else:
                    print("  no response")

            elif cmd_name == "ver":
                v = ctrl.get_version()
                if v:
                    for k, val in v.items():
                        print(f"  {k}: {val}")
                else:
                    print("  no response")

            elif cmd_name == "info":
                info = ctrl.get_all_info()
                for k, v in info.items():
                    if v:
                        if isinstance(v, dict):
                            items = []
                            for vk, vv in v.items():
                                if isinstance(vv, bool):
                                    items.append(f"{vk}={'ON' if vv else 'OFF'}")
                                elif isinstance(vv, int) and vk in ("status",):
                                    items.append(f"{vk}=0x{vv:08X}")
                                else:
                                    items.append(f"{vk}={vv}")
                            print(f"  {k}: {', '.join(items)}")
                        else:
                            print(f"  {k}: {v}")
                    else:
                        print(f"  {k}: (no response)")

            elif cmd_name == "greet":
                if len(parts) >= 2:
                    enable = parts[1].lower() in ("on", "1", "true", "yes")
                    r = ctrl.set_greet(enable)
                    if r and r.get("success"):
                        print(f"  Voice prompts: {'ON' if enable else 'OFF'} (set ok)")
                    elif r:
                        print(f"  Voice prompts: set failed ({r})")
                    else:
                        print("  no response")
                else:
                    r = ctrl.get_greet_setting()
                    if r and "enabled" in r:
                        print(f"  Voice prompts: {'ON' if r['enabled'] else 'OFF'}")
                    elif r and "status" in r:
                        print(f"  Voice prompts: status=0x{r['status']:08X}")
                    elif r:
                        print(f"  Voice prompts: {r}")
                    else:
                        print("  no response")

            elif cmd_name == "wear":
                if len(parts) >= 2:
                    enable = parts[1].lower() in ("on", "1", "true", "yes")
                    r = ctrl.set_wear(enable)
                    if r and r.get("success"):
                        print(f"  Wear detection: {'ON' if enable else 'OFF'} (set ok)")
                    elif r:
                        print(f"  Wear detection: set failed ({r})")
                    else:
                        print("  no response")
                else:
                    r = ctrl.get_wear_setting()
                    if r and "enabled" in r:
                        print(f"  Wear detection: {'ON' if r['enabled'] else 'OFF'}")
                    elif r:
                        print(f"  Wear detection: {r}")
                    else:
                        print("  no response")

            elif cmd_name == "ivol":
                if len(parts) >= 2:
                    enable = parts[1].lower() in ("on", "1", "true", "yes")
                    r = ctrl.set_intellect_volume(enable)
                    if r and r.get("success"):
                        print(
                            f"  Intellect volume: {'ON' if enable else 'OFF'} (set ok)"
                        )
                    elif r:
                        print(f"  Intellect volume: set failed ({r})")
                    else:
                        print("  no response")
                else:
                    r = ctrl.get_intellect_volume()
                    if r and "enabled" in r:
                        print(f"  Intellect volume: {'ON' if r['enabled'] else 'OFF'}")
                    elif r:
                        print(f"  Intellect volume: {r}")
                    else:
                        print("  no response")

            elif cmd_name == "save":
                if len(parts) >= 2:
                    enable = parts[1].lower() in ("on", "1", "true", "yes")
                    r = ctrl.set_saving_mode(enable)
                    if r and r.get("success"):
                        print(f"  Saving mode: {'ON' if enable else 'OFF'} (set ok)")
                    elif r:
                        print(f"  Saving mode: set failed ({r})")
                    else:
                        print("  no response")
                else:
                    r = ctrl.get_saving_mode()
                    if r and "enabled" in r:
                        print(f"  Saving mode: {'ON' if r['enabled'] else 'OFF'}")
                    elif r:
                        print(f"  Saving mode: {r}")
                    else:
                        print("  no response")

            elif cmd_name in ("lp", "sp", "slide", "dc"):
                gesture_map = {
                    "lp": (
                        "long press",
                        ctrl.get_long_press_action,
                        ctrl.set_long_press_action,
                    ),
                    "sp": (
                        "short press",
                        ctrl.get_short_press_action,
                        ctrl.set_short_press_action,
                    ),
                    "slide": ("slide", ctrl.get_slide_action, ctrl.set_slide_action),
                    "dc": (
                        "double click",
                        ctrl.get_double_click_action,
                        ctrl.set_double_click_action,
                    ),
                }
                glabel, gget, gset = gesture_map[cmd_name]
                if len(parts) >= 3:
                    try:
                        side = int(parts[1])
                        action = int(parts[2])
                        r = gset(side, action)
                        if r and r.get("success"):
                            act_name = GESTURE_ACTIONS.get(action, f"action {action}")
                            side_name = "Left" if side == 1 else "Right"
                            print(f"  {glabel}: {side_name} -> {act_name} (set ok)")
                        elif r:
                            print(f"  {glabel}: set failed ({r})")
                        else:
                            print(f"  no response")
                    except ValueError:
                        print(f"  Usage: {cmd_name} <side(1|2)> <action>")
                else:
                    r = gget()
                    if r:
                        if "action" in r or "side" in r:
                            sn = r.get("side_name", f"side={r.get('side', '?')}")
                            an = r.get("action_name", f"action={r.get('action', '?')}")
                            print(f"  {glabel}: {sn} -> {an}")
                        elif "status" in r:
                            print(f"  {glabel}: status=0x{r['status']:08X}")
                        else:
                            print(f"  {glabel}: {r}")
                    else:
                        print(f"  no response")

            elif cmd_name == "lang":
                if len(parts) >= 2:
                    lang_code = parts[1]
                    r = ctrl.set_language(lang_code)
                    if r:
                        if r.get("success"):
                            print(f"  Language set to {lang_code} (OK)")
                        else:
                            print(
                                f"  Language set failed: status=0x{r.get('status', 0):08X}"
                            )
                            lang_info = ctrl.get_language_setting()
                            if lang_info:
                                support = lang_info.get("tag3", "")
                                if support and lang_code not in support:
                                    print(f"  Supported languages: {support}")
                                    print(f"  Try one of: {support}")
                    else:
                        print("  no response")
                else:
                    r = ctrl.get_language_setting()
                    if r:
                        for k, v in r.items():
                            print(f"  {k}: {v}")
                        support = r.get("tag3", "")
                        if support:
                            langs = [l.strip() for l in support.split(",")]
                            print(f"  Supported: {', '.join(langs)}")
                    else:
                        print("  no response")

            elif cmd_name == "raw" and len(parts) >= 2:
                try:
                    b = bytes.fromhex(parts[1].replace(" ", ""))
                    frames = ctrl.send_command(
                        b, args.timeout if hasattr(args, "timeout") else 2.0
                    )
                    for f in frames:
                        print(
                            f"  svc=0x{f['svc']:02X} cmd=0x{f['cmd']:02X} data={f['data'].hex()}"
                        )
                except ValueError as e:
                    print(f"  Error: {e}")

            else:
                print(f"  Unknown: {cmd_name}")

        except Exception as e:
            print(f"  Error: {e}")

        print()

    ctrl.disconnect()


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--debug", action="store_true")

    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("scan", help="Scan for FreeBuds")
    p.add_argument("-t", "--time", type=int, default=10)
    p.add_argument("--save")

    p = sub.add_parser("run", help="Run interactive commands non-interactively")
    p.add_argument("-a", "--address")
    p.add_argument(
        "commands",
        nargs="+",
        help="Commands to run (e.g. 'bat' 'lang' 'greet on' 'lp 1 2')",
    )
    p.add_argument("-t", "--timeout", type=float, default=2.0)

    p = sub.add_parser("interactive", help="Interactive shell")
    p.add_argument("-a", "--address")
    p.add_argument("-t", "--timeout", type=float, default=2.0)

    args = parser.parse_args()
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "interactive":
        cmd_interactive(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
