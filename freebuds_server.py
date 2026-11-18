#!/usr/bin/env python3
# Copyright (c) 2026 Majaahh
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import freebuds_controller as fb

log = logging.getLogger("freebuds-server")

_ctrl = fb.FreeBudsController()
_lock = threading.RLock()


def _resolve_mode(value):
    if isinstance(value, int):
        return value if value in fb.NC_MODES else None
    if isinstance(value, str):
        v = value.strip().lower()
        if v.isdigit():
            return int(v) if int(v) in fb.NC_MODES else None
        return fb.NC_MODE_ALIASES.get(v)
    return None


def _resolve_level(value):
    if isinstance(value, int):
        return value if value in fb.NC_LEVELS else None
    if isinstance(value, str):
        v = value.strip().lower()
        if v.isdigit():
            return int(v) if int(v) in fb.NC_LEVELS else None
        return fb.NC_LEVEL_ALIASES.get(v)
    return None


def _resolve_side(value):
    return {"1": 1, "2": 2, "l": 1, "left": 1, "r": 2, "right": 2}.get(str(value).lower())


def _resolve_action(gesture_key: str, value):
    actions = fb.GESTURE_TYPES[gesture_key]["actions"]
    if isinstance(value, int):
        return value if value in actions or value == 255 else None
    if isinstance(value, str):
        v = value.strip()
        if v.isdigit():
            n = int(v)
            return n if n in actions or n == 255 else None
        for num, label in actions.items():
            if label.lower() == v.lower():
                return num
    return None


def _ok(data) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def _err(status: int, message: str):
    return status, json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")


def _public_version(version):
    return {key: version[key] for key in ("model", "firmware", "ota_package") if key in (version or {})}


def _connect(payload: dict):
    mac = (payload.get("mac") or fb.load_mac() or "").strip()
    if not mac:
        return _err(400, "No MAC address provided")
    try:
        with _lock:
            ok = _ctrl.connect(mac)
        if not ok:
            return _err(502, "Connect failed")
        return 200, _ok({"connected": True, "mac": mac})
    except ValueError as e:
        return _err(400, str(e))
    except Exception as e:
        log.exception("connect failed")
        return _err(500, f"Connect error: {e}")


def _read_json(handler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    if not length:
        return {}
    raw = handler.rfile.read(length)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def build_meta() -> dict:
    gestures = {}
    for key, gt in fb.GESTURE_TYPES.items():
        gestures[key] = {
            "name": gt["name"],
            "call_actions": fb.CALL_ACTIONS.get(key, {}),
            "scope": "global" if key == "slide" else "per_side",
            "actions": {str(n): label for n, label in gt["actions"].items()},
        }
    features = {}
    for fkey, fentry in fb.FEATURES.items():
        features[fkey] = {
            "name": fentry["name"],
            "settable": "set" in fentry,
        }
    return {
        "noise_cycles": fb.NOISE_CYCLES,
        "nc_modes": {str(n): name for n, name in fb.NC_MODES.items()},
        "nc_levels": {str(n): name for n, name in fb.NC_LEVELS.items()},
        "sides": {"1": "Left", "2": "Right"},
        "gestures": gestures,
        "features": features,
        "eq_modes": {str(n): name for n, name in fb.EQ_MODES.items()},
    }


def _devices():
    return [
        {k: v for k, v in device.items() if k != "byte_addr"}
        for device in _ctrl.get_bonded_devices()
    ]


class Handler(BaseHTTPRequestHandler):
    server_version = "FreeBudsServer/1.0"

    def log_message(self, fmt, *args):
        log.debug("%s %s" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _send_result(self, key, result, **fields):
        if not result or result.get("success") is not True:
            detail = (result or {}).get("error") or (result or {}).get("status", "unconfirmed")
            return self._send(502, _ok({"error": f"Device did not confirm change ({detail})"}))
        return self._send(200, _ok({key: result, **fields}))

    def _handle(self, method: str):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)

        try:
            if path == "/api/meta" and method == "GET":
                return self._send(200, _ok(build_meta()))

            if path == "/api/status" and method == "GET":
                return self._send(
                    200, _ok({"connected": bool(_ctrl._connected), "mac": _ctrl.mac_address})
                )

            if path == "/api/connect" and method == "POST":
                code, body = _connect(_read_json(self))
                return self._send(code, body)

            if path == "/api/disconnect" and method == "POST":
                with _lock:
                    _ctrl.disconnect()
                return self._send(200, _ok({"connected": False}))

            if path == "/api/scan" and method == "GET":
                t = int((query.get("time") or ["5"])[0])
                devices = fb.scan_freebuds(scan_time=max(1, min(t, 30)))
                return self._send(200, _ok({"devices": devices}))

            if not _ctrl._connected:
                return self._send(503, _ok({"error": "Not connected to a device"}))

            if path == "/api/battery" and method == "GET":
                return self._send(200, _ok({"battery": _ctrl.get_battery()}))

            if path == "/api/version" and method == "GET":
                return self._send(200, _ok({"version": _public_version(_ctrl.get_version())}))

            if path == "/api/anc" and method == "GET":
                return self._send(200, _ok({"anc": _ctrl.get_noise_mode()}))

            if path == "/api/anc" and method == "POST":
                body = _read_json(self)
                mode = _resolve_mode(body.get("mode"))
                if mode is None:
                    return self._send(400, _ok({"error": "Invalid ANC mode"}))
                level = body.get("level")
                if level is None:
                    result = _ctrl.set_noise_mode(mode)
                else:
                    if mode != fb.NC_MODE_ON:
                        return self._send(
                            400,
                            _ok({"error": "ANC level requires noise cancelling mode"}),
                        )
                    level = _resolve_level(level)
                    if level is None:
                        return self._send(400, _ok({"error": "Invalid ANC level"}))
                    result = _ctrl.set_anc_state_extended(mode, level)
                return self._send_result("anc", result)

            if path == "/api/devices" and method == "GET":
                return self._send(200, _ok({"devices": _devices()}))

            if path == "/api/devices" and method == "POST":
                body = _read_json(self)
                operations = {
                    "connect": _ctrl.connect_device,
                    "disconnect": _ctrl.disconnect_device,
                    "primary": _ctrl.set_primary_device,
                    "unpair": _ctrl.unpair_device,
                }
                operation = operations.get(str(body.get("action")))
                target = str(body.get("target", ""))
                preference = str(body.get("action"))
                is_preference = preference in ("reconnect", "audio-switch")
                if is_preference and type(body.get("enabled")) is not bool:
                    return self._send(400, _ok({"error": "Expected boolean enabled"}))
                if (not operation and not is_preference) or not target:
                    return self._send(
                        400, _ok({"error": "Expected action and device MAC or index"})
                    )
                mac = _ctrl._resolve_bonded_mac(target)
                if not mac:
                    return self._send(400, _ok({"error": "Unknown device target"}))
                if is_preference:
                    return self._send_result(
                        "device",
                        _ctrl.set_device_preference(mac, preference, body["enabled"]),
                    )
                return self._send_result("device", operation(mac))

            if path == "/api/fit" and method == "POST":
                return self._send_result("fit", _ctrl.run_fit_test())

            if path == "/api/noise-cycle" and method == "GET":
                return self._send(
                    200, _ok({"cycle": _ctrl.get_noise_control_setting()})
                )

            if path == "/api/noise-cycle" and method == "POST":
                body = _read_json(self)
                side = _resolve_side(body.get("side"))
                cycle = body.get("cycle")
                if (
                    side is None
                    or type(cycle) is not int
                    or cycle not in fb.NOISE_CYCLES
                ):
                    return self._send(
                        400, _ok({"error": "Expected side and stock cycle number 1-4"})
                    )
                return self._send_result(
                    "cycle",
                    _ctrl.set_noise_control_setting(
                        cycle if side == 1 else None, cycle if side == 2 else None
                    ),
                )

            if path == "/api/gestures" and method == "GET":
                gestures = {}
                for key in fb.GESTURE_TYPES:
                    gestures[key] = _ctrl.get_gesture_action(key)
                return self._send(200, _ok({"gestures": gestures}))

            if path == "/api/gesture" and method == "POST":
                body = _read_json(self)
                key = fb.GESTURE_ALIASES.get(str(body.get("gesture", "")).lower())
                if not key:
                    return self._send(400, _ok({"error": "Unknown gesture"}))
                if body.get("side") == "call":
                    action = body.get("action")
                    if (
                        key not in fb.CALL_SETTERS
                        or type(action) is not int
                        or action not in (0, 255)
                    ):
                        return self._send(
                            400, _ok({"error": "Expected in-call action 0 or 255"})
                        )
                    return self._send_result(
                        "result", _ctrl.set_call_gesture(key, action), gesture=key
                    )
                side = (
                    0
                    if key == "slide" and body.get("side") == "both"
                    else _resolve_side(body.get("side"))
                )
                if side is None:
                    return self._send(400, _ok({"error": "Invalid side (1=left, 2=right)"}))
                action = _resolve_action(key, body.get("action"))
                if action is None:
                    return self._send(400, _ok({"error": "Invalid action for gesture"}))
                result = _ctrl.set_gesture_action(key, side, action)
                return self._send_result("result", result, gesture=key, side=side)

            if path == "/api/features" and method == "GET":
                features = {fkey: _ctrl.get_feature(fkey) for fkey in fb.FEATURES}
                return self._send(200, _ok({"features": features}))

            if path == "/api/feature" and method == "POST":
                body = _read_json(self)
                name = str(body.get("name", "")).strip()
                if name not in fb.FEATURES or "set" not in fb.FEATURES[name]:
                    return self._send(400, _ok({"error": "Unknown or read-only feature"}))
                enabled = body.get("enabled")
                if not isinstance(enabled, bool):
                    return self._send(400, _ok({"error": "Expected a boolean enabled value"}))
                result = _ctrl.set_feature(name, enabled)
                return self._send_result("result", result, feature=name)

            if path == "/api/locator" and method == "GET":
                return self._send(
                    200,
                    _ok(
                        {
                            "locator": {
                                side: _ctrl.locator(side) for side in ("left", "right")
                            }
                        }
                    ),
                )

            if path == "/api/locator" and method == "POST":
                body = _read_json(self)
                if body.get("side") not in ("left", "right") or not isinstance(body.get("ring"), bool):
                    return self._send(400, _ok({"error": "Expected side and boolean ring"}))
                return self._send_result("locator", _ctrl.locator(body["side"], body["ring"]))

            if path == "/api/sfx" and method == "GET":
                return self._send(200, _ok({"sfx": _ctrl.get_sound_effect()}))

            if path == "/api/sfx" and method == "POST":
                body = _read_json(self)
                mode = fb.resolve_eq_mode(body.get("mode"))
                if mode is None:
                    return self._send(400, _ok({"error": "Invalid EQ mode"}))
                return self._send_result("sfx", _ctrl.set_sound_effect(mode))

            if path == "/api/language" and method == "GET":
                return self._send(200, _ok({"language": _ctrl.get_language_setting()}))

            if path == "/api/language" and method == "POST":
                body = _read_json(self)
                code = str(body.get("code", "")).strip()[:16]
                if not code:
                    return self._send(400, _ok({"error": "Missing language code"}))
                return self._send_result("language", _ctrl.set_language(code))

            if path == "/api/info" and method == "GET":
                info = _ctrl.get_all_info()
                info["version"] = _public_version(info["version"])
                info["locator"] = {side: _ctrl.locator(side) for side in ("left", "right")}
                info["devices"] = _devices()
                return self._send(200, _ok({"info": info}))

            return self._send(404, _ok({"error": f"No such endpoint: {method} {path}"}))

        except Exception as e:  # noqa: BLE001
            log.exception("handler crashed")
            try:
                self._send(500, _ok({"error": f"Server error: {e}"}))
            except Exception:
                pass

    def do_GET(self):
        with _lock:
            self._handle("GET")

    def do_POST(self):
        with _lock:
            self._handle("POST")


def main():
    parser = argparse.ArgumentParser(description="FreeBuds HTTP backend")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765, help="Port (default 8765)")
    parser.add_argument("--mac", help="MAC to connect at startup")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger("freebuds").setLevel(logging.DEBUG)
        logging.getLogger("freebuds-server").setLevel(logging.DEBUG)
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.mac:
        with _lock:
            if not _ctrl.connect(args.mac):
                log.warning("Could not connect to %s at startup", args.mac)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    log.info("FreeBuds server listening on http://%s:%d", args.host, args.port)
    log.info("Meta: %s", json.dumps(build_meta())[:200])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        with _lock:
            _ctrl.disconnect()


if __name__ == "__main__":
    main()
