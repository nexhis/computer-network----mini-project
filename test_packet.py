import unittest
from packet import *

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


if __name__ == "__main__":
    unittest.main()
