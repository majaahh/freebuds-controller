#!/usr/bin/env python3
# Copyright (c) 2026 Majaahh
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import sys
from pathlib import Path
from time import sleep

from download_ota import connected_5i

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import freebuds_controller as fb  # noqa: E402


def change(label, read, write, original, target, prompt=None):
    if original is None or target is None or target == original:
        print(f"{label}: skipped (no restorable alternative)", flush=True)
        return True
    print(f"{label}: {original} -> {target}", flush=True)
    try:
        write(target)
        observed = read()
        passed = observed == target
        print(f"  Readback: {observed} ({'PASS' if passed else 'FAIL'})", flush=True)
        if passed and prompt:
            answer = input(f"  {prompt} Did you notice the effect? [y/n/skip] ")
            if answer.strip().lower() in ("y", "n"):
                passed = answer.strip().lower() == "y"
    finally:
        for _ in range(2):
            write(original)
            if read() == original:
                print("  Restore: PASS", flush=True)
                break
        else:
            raise RuntimeError(
                f"{label}: restore could not be verified (original: {original})"
            )
    return passed


def other(original, options):
    return next((value for value in options if value != original), None)


def readback(ctrl, interactive):
    def test(label, getter, field, setter, choices, prompt=None):
        state = getter() or {}
        original = state.get(field)
        options = state.get(choices, ()) if isinstance(choices, str) else choices
        return change(
            label,
            lambda: (getter() or {}).get(field),
            setter,
            original,
            other(original, options),
            prompt if interactive else None,
        )

    ok = test(
        "EQ preset",
        ctrl.get_sound_effect,
        "mode",
        ctrl.set_sound_effect,
        "modes",
        "Listen to music.",
    )
    for gesture in ("dc", "lp"):
        ok &= test(
            f"{gesture} in-call action",
            lambda: ctrl.get_gesture_action(gesture),
            "call_action",
            lambda value: ctrl.set_call_gesture(gesture, value),
            "call_supported",
        )
    ok &= test(
        "Global slide",
        ctrl.get_slide_action,
        "global",
        lambda value: ctrl.set_slide_action(0, value),
        "supported",
        "Swipe up or down on either bud during playback.",
    )
    for side in ("left", "right"):
        state = ctrl.get_noise_control_setting() or {}
        original = state.get(side)
        options = [
            code for code in fb.NOISE_CYCLES if code in state.get("supported", ())
        ]
        if original not in options:
            print(f"{side.title()} noise cycle: skipped (original setting unavailable)")
            continue
        ok &= test(
            f"{side.title()} noise cycle",
            ctrl.get_noise_control_setting,
            side,
            lambda value: (
                ctrl.set_noise_control_setting(value, None)
                if side == "left"
                else ctrl.set_noise_control_setting(None, value)
            ),
            options,
        )
    state = ctrl.query_noise_reduction_mode() or {}
    mode, level = state.get("mode"), state.get("submode")
    if mode == fb.NC_MODE_ON and level in fb.NC_LEVELS:
        options = [fb.NC_LEVEL_COZY, fb.NC_LEVEL_ULTRA]
        if (ctrl.get_dynamic_anc_support() or {}).get("supported"):
            options.insert(0, fb.NC_LEVEL_DYNAMIC)
        ok &= test(
            "ANC strength",
            ctrl.query_noise_reduction_mode,
            "level",
            ctrl.set_anc_level,
            options,
            "Listen for a change in background noise.",
        )
    elif (mode == fb.NC_MODE_OFF and level == 0) or (
        mode == fb.NC_MODE_AWARE and level in (1, 2)
    ):

        def read_mode():
            state = ctrl.query_noise_reduction_mode() or {}
            return state.get("mode"), state.get("submode")

        target = (
            (fb.NC_MODE_AWARE, 2) if mode == fb.NC_MODE_OFF else (fb.NC_MODE_OFF, 0)
        )
        ok &= change(
            "Noise control mode and submode",
            read_mode,
            lambda value: ctrl.set_anc_state_extended(*value),
            (mode, level),
            target,
            "Listen for a change in background noise." if interactive else None,
        )
    else:
        print("Noise control: skipped (original setting could not be restored)")
    return ok


def reconnection(ctrl):
    field = "back_conn_permit"
    device = next(
        (
            d
            for d in ctrl.get_bonded_devices()
            if d.get("conn_state") == 0
            and d.get(field) in (0, 1)
            and not d.get("primary")
        ),
        None,
    )
    if device is None:
        print("Automatic reconnection: skipped (no idle secondary device)")
        return True
    address = device["addr"]

    def read():
        return next(
            (d.get(field) for d in ctrl.get_bonded_devices() if d["addr"] == address),
            None,
        )

    original = device[field]
    return change(
        "Automatic reconnection",
        read,
        lambda flag: ctrl.set_device_preference(address, "reconnect", bool(flag)),
        original,
        1 - original,
    )


def listen(ctrl):
    ok = True
    for side in ("left", "right"):
        answer = input(
            f"Take the {side} bud out of your ear. Ring it for 2 seconds? [y/N] "
        )
        if answer.strip().lower() != "y":
            continue
        current = ctrl.locator(side) or {}
        if current.get("ringing") is not False:
            print(
                f"{side.title()} locator: skipped (initial state not confirmed silent)"
            )
            continue
        try:
            result = ctrl.locator(side, True) or {}
            if result.get("success"):
                sleep(2)
            else:
                print(result.get("error", "Ring request unconfirmed"))
        finally:
            stopped = (ctrl.locator(side, False) or {}).get("success")
            if not stopped:
                raise RuntimeError(
                    f"{side.title()} locator: stop could not be confirmed"
                )
        ok &= bool(result.get("success"))
        if result.get("success"):
            ok &= input("Did you hear the ring? [y/N] ").lower() == "y"
    if input("Wear both buds. Run the ear-tip fit test? [y/N] ").lower() == "y":
        result = ctrl.run_fit_test()
        print(f"Fit: {result}")
        ok &= result.get("success") is True
    return ok


def main():
    parser = argparse.ArgumentParser(
        description="Check FreeBuds 5i controls and restore settings"
    )
    parser.add_argument(
        "--address", help="Override automatic connected-device detection"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--interactive",
        action="store_true",
        help="Ask for audible checks and offer locator and fit tests",
    )
    mode.add_argument(
        "--audio-only", action="store_true", help="Offer just the locator and fit tests"
    )
    args = parser.parse_args()
    ctrl = fb.FreeBudsController(args.address or connected_5i())
    if not ctrl.connect():
        return 1
    try:
        if args.audio_only:
            return 0 if listen(ctrl) else 1
        ok = readback(ctrl, args.interactive)
        ok &= reconnection(ctrl)
        if args.interactive:
            ok &= listen(ctrl)
        return 0 if ok else 1
    finally:
        ctrl.disconnect()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except (EOFError, RuntimeError, ValueError, OSError) as exc:
        sys.exit(str(exc))
