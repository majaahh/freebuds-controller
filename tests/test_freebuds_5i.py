import io
import json
import unittest
from unittest.mock import Mock, patch

import freebuds_controller as fb
import freebuds_server as server


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.ctrl = fb.FreeBudsController("00:00:00:00:00:00")

    def replay(self, exchanges):
        pending = iter(exchanges)

        def send(payload, *args):
            request, response = next(pending)
            self.assertEqual(payload.hex(), request)
            return [
                {"svc": payload[0], "cmd": payload[1], "data": bytes.fromhex(response)}
            ]

        self.ctrl.send_command = send
        self.addCleanup(lambda: self.assertEqual(list(pending), []))

    def test_call_action_and_readback(self):
        state = "010101020101030501070200ff040100060200ff"
        query = "0120010002000300"
        self.replay(
            [
                (query, state),
                ("011f0401ff", "060100"),
                (query, state.replace("040100", "0401ff")),
            ]
        )
        self.assertTrue(self.ctrl.set_call_gesture("dc", 255)["success"])

    def test_slide_stock_packet(self):
        self.replay(
            [
                ("2b1f010002000300", "010100030200ff"),
                ("2b1e0101ff0202ff", "030100"),
                ("2b1f010002000300", "0101ff030200ff"),
            ]
        )
        self.assertTrue(self.ctrl.set_slide_action(0, 255)["success"])

    def test_noise_cycle_right_only(self):
        query = "2b1901000200"
        state = "010103020103030a0102030405060708090a"
        self.replay(
            [
                (query, state),
                ("2b18020104", "7f04000186a0"),
                (query, state.replace("020103", "020104")),
            ]
        )
        self.assertTrue(self.ctrl.set_noise_control_setting(None, 4)["success"])

    def test_reject_nonstock_long_press(self):
        self.replay(
            [("2b17010002000300", "01010a02010a030d000102030405060708090a0e0f")]
        )
        self.assertIsNone(self.ctrl.set_long_press_action(1, 1))

    def test_device_preference_capability(self):
        self.ctrl.get_bonded_devices = Mock(
            return_value=[{"byte_addr": bytes(6), "back_conn_permit": 1}]
        )
        self.replay([("2b330506000000000000", "1e01051f0100")])
        self.assertFalse(
            self.ctrl.set_device_preference(
                self.ctrl.mac_address, "audio-switch", True
            )["success"]
        )
        self.assertTrue(
            self.ctrl.set_device_preference(self.ctrl.mac_address, "reconnect", False)[
                "success"
            ]
        )

    def test_awareness_is_not_anc_intensity(self):
        self.replay([("2b2a0100", "01020202")])
        result = self.ctrl.query_noise_reduction_mode()
        self.assertEqual(result["awareness_name"], "Awareness")
        self.assertNotIn("level", result)

    def test_fit_reports_and_cleanup(self):
        self.ctrl._connected = True
        self.ctrl.sock = Mock()
        left = fb.build_frame(bytes.fromhex("2b27010101"))
        right = fb.build_frame(bytes.fromhex("2b27010102"))
        self.ctrl.sock.recv.side_effect = [left + right[:4], right[4:]]
        self.replay(
            [
                ("2b2501000200", "010101020101"),
                ("2b370100", "010101"),
                ("2b260100", "020100"),
                ("2b260300", "7f04000186a0"),
            ]
        )
        with (
            patch.object(fb, "fit_audio", return_value="/test.ogg"),
            patch.object(fb.shutil, "which", return_value="available"),
            patch.object(
                fb.subprocess,
                "check_output",
                return_value="1 bluez_output.00_00_00_00_00_00.1",
            ),
            patch.object(fb.subprocess, "Popen") as player,
        ):
            player.return_value.poll.side_effect = [None, None, 0, 0]
            self.assertEqual(
                self.ctrl.run_fit_test(),
                {"success": True, "left": "adjust", "right": "good"},
            )
            player.return_value.terminate.assert_not_called()

    def test_fit_requires_both_buds(self):
        self.ctrl._connected = True
        self.replay([("2b2501000200", "010101020100")])
        with (
            patch.object(fb, "fit_audio"),
            patch.object(fb.shutil, "which", return_value="available"),
            patch.object(
                fb.subprocess,
                "check_output",
                return_value="1 bluez_output.00_00_00_00_00_00.1",
            ),
            patch.object(fb.subprocess, "Popen") as player,
        ):
            self.assertFalse(self.ctrl.run_fit_test()["success"])
            player.assert_not_called()

    def test_rejected_cycle_is_not_confirmed(self):
        self.replay(
            [
                ("2b1901000200", "010103020103030401020304"),
                ("2b18010101", "7f04000186a3"),
            ]
        )
        self.assertFalse(self.ctrl.set_noise_control_setting(1)["success"])

    def test_fit_report_cleanup_on_playback_failure(self):
        self.ctrl._connected = True
        self.replay(
            [
                ("2b2501000200", "010101020101"),
                ("2b370100", "010101"),
                ("2b260100", "020100"),
                ("2b260300", "7f04000186a0"),
            ]
        )
        with (
            patch.object(fb, "fit_audio"),
            patch.object(fb.shutil, "which", return_value="available"),
            patch.object(
                fb.subprocess,
                "check_output",
                return_value="1 bluez_output.00_00_00_00_00_00.1",
            ),
            patch.object(fb.subprocess, "Popen") as player,
        ):
            player.return_value.poll.return_value = 1
            self.assertEqual(
                self.ctrl.run_fit_test()["error"], "Test audio playback failed"
            )

    def test_http_call_post_and_read_only_get(self):
        handler = object.__new__(server.Handler)
        handler._send = Mock()
        with patch.object(server, "_ctrl") as ctrl:
            handler.path = "/api/gesture"
            body = json.dumps({"gesture": "lp", "side": "call", "action": 0}).encode()
            handler.headers = {"Content-Length": len(body)}
            handler.rfile = io.BytesIO(body)
            ctrl.set_call_gesture.return_value = {"success": True}
            handler._handle("POST")
            ctrl.set_call_gesture.assert_called_once_with("long_press", 0)
            self.assertEqual(handler._send.call_args.args[0], 200)
            handler.path = "/api/features"
            ctrl.get_feature.return_value = {}
            handler._handle("GET")
            self.assertNotIn(unittest.mock.call("fit"), ctrl.get_feature.call_args_list)
            ctrl.run_fit_test.assert_not_called()


if __name__ == "__main__":
    unittest.main()
