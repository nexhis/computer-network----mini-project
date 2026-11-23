import unittest
import io
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from packet import *
from host import send_echo, run_comparison

"""
TESTS FOR packet.py
"""


class TestRoundTrip(unittest.TestCase):

    def test_text_payload(self):
        packet = Packet(1, 2, DEFAULT_HOP_LIMIT, DATA, 7, "hi".encode())
        data = encode(packet)
        self.assertEqual(len(data), HEADER_SIZE + 2)
        self.assertEqual(decode(data), packet)

    def test_every_message_type(self):
        for msg_type in MSG_TYPES:
            packet = Packet(1, 2, DEFAULT_HOP_LIMIT, msg_type, 1, b"x")
            self.assertEqual(decode(encode(packet)), packet)

    def test_empty_payload(self):
        packet = Packet(1, 2, DEFAULT_HOP_LIMIT, DATA, 1, b"")
        self.assertEqual(decode(encode(packet)), packet)

    def test_max_payload(self):
        packet = Packet(1, 2, DEFAULT_HOP_LIMIT, DATA, 1, b"x" * MAX_PAYLOAD_SIZE)
        data = encode(packet)
        self.assertEqual(len(data), MAX_PACKET_SIZE)
        self.assertEqual(decode(data), packet)


class TestDecodeRejects(unittest.TestCase):

    def test_empty(self):
        with self.assertRaises(PacketError):
            decode(b"")

    def test_too_short(self):
        with self.assertRaises(PacketError):
            decode(b"x" * (HEADER_SIZE - 1))

    def test_too_big(self):
        with self.assertRaises(PacketError):
            decode(b"x" * (MAX_PACKET_SIZE + 1))

    def test_unknown_type(self):
        # src=1, dst=2, hop_limit=16, msg_type=9, msg_id=1
        with self.assertRaises(PacketError):
            decode(bytes([0, 1, 0, 2, 16, 9, 0, 0, 0, 1]))

    def test_hop_limit_zero_is_decoded_for_router_drop_logging(self):
        packet = Packet(1, 2, 0, DATA, 1, b"")
        self.assertEqual(decode(encode(packet)), packet)


class TestEncodeRefuses(unittest.TestCase):

    def test_address_too_big(self):
        with self.assertRaises(PacketError):
            encode(Packet(70000, 2, DEFAULT_HOP_LIMIT, DATA, 1, b""))

    def test_payload_too_big(self):
        with self.assertRaises(PacketError):
            encode(Packet(1, 2, DEFAULT_HOP_LIMIT, DATA, 1, b"x" * (MAX_PAYLOAD_SIZE + 1)))

    def test_unknown_type(self):
        with self.assertRaises(PacketError):
            encode(Packet(1, 2, DEFAULT_HOP_LIMIT, 9, 1, b""))


class TestEchoComparison(unittest.TestCase):
    def setUp(self):
        self.config = {
            "H1": {"type": "host", "vaddr": 1, "port": 5001, "neighbors": ["RA"]},
            "H2": {"type": "host", "vaddr": 2, "port": 5002, "neighbors": ["RD"]},
            "RA": {"port": 5011, "neighbors": ["H1"]},
        }
        self.socket = Mock()

    def test_send_echo_reports_matching_reply_and_rtt(self):
        reply = Packet(2, 1, DEFAULT_HOP_LIMIT, ECHO_REPLY, 123, b"ping")

        def receive_reply(*args, **kwargs):
            data = encode(reply)
            return data, ("127.0.0.1", 5002)

        original_recvfrom = Mock(side_effect=receive_reply)
        self.socket.recvfrom = original_recvfrom
        self.socket.sendto = Mock()

        with patch("host.time.time_ns", return_value=123):
            output = io.StringIO()
            with redirect_stdout(output):
                rtt = send_echo("H1", self.config, self.socket, 2, "ping", 1.0)

        self.assertIsNotNone(rtt)
        self.assertIn("REPLY", output.getvalue())
        self.assertIn("payload=MATCH", output.getvalue())

    def test_comparison_prints_sender_summary(self):
        output = io.StringIO()
        with patch("host.send_echo", return_value=2.5):
            with redirect_stdout(output):
                run_comparison(
                    "H1",
                    self.config,
                    self.socket,
                    2,
                    "ping",
                    1.0,
                    3,
                    0.0,
                    "RB",
                )

        summary = output.getvalue()
        self.assertIn("sent=3 received=3 lost=0", summary)
        self.assertIn("success=100.0%", summary)
        self.assertIn("avg=2.500ms", summary)


if __name__ == "__main__":
    unittest.main()
