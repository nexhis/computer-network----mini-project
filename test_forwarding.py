import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock

from packet import DATA, Packet, decode
from router import forward_packet


class TestRouterForwarding(unittest.TestCase):
    def setUp(self):
        self.config = {
            "RA": {
                "neighbors": ["RB"],
                "routes": {"2": "RB"},
            },
            "RB": {"port": 5012},
        }
        self.server_socket = Mock()

    def test_forwards_and_decrements_hop_limit_without_changing_payload(self):
        packet = Packet(1, 2, 4, DATA, 17, b"\x00payload")

        forward_packet("RA", self.config, packet, self.server_socket)

        self.server_socket.sendto.assert_called_once()
        data, address = self.server_socket.sendto.call_args.args
        self.assertEqual(decode(data), Packet(1, 2, 3, DATA, 17, b"\x00payload"))
        self.assertEqual(address, ("127.0.0.1", 5012))

    def test_drops_exhausted_hop_limit(self):
        packet = Packet(1, 2, 1, DATA, 17, b"payload")
        output = io.StringIO()

        with redirect_stdout(output):
            forward_packet("RA", self.config, packet, self.server_socket)

        self.server_socket.sendto.assert_not_called()
        self.assertIn("exhausted hop limit", output.getvalue())

    def test_drops_unknown_destination(self):
        packet = Packet(1, 3, 4, DATA, 17, b"payload")
        output = io.StringIO()

        with redirect_stdout(output):
            forward_packet("RA", self.config, packet, self.server_socket)

        self.server_socket.sendto.assert_not_called()
        self.assertIn("unknown destination", output.getvalue())

    def test_drops_invalid_next_hop(self):
        packet = Packet(1, 2, 4, DATA, 17, b"payload")
        self.config["RA"]["routes"]["2"] = "RC"
        output = io.StringIO()

        with redirect_stdout(output):
            forward_packet("RA", self.config, packet, self.server_socket)

        self.server_socket.sendto.assert_not_called()
        self.assertIn("invalid next hop", output.getvalue())


if __name__ == "__main__":
    unittest.main()
