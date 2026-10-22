import io
import time
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock

import network
from packet import DATA, Packet, decode
from network import send_over_link


class TestLinkConditions(unittest.TestCase):
    def setUp(self):
        self.config = {
            "RA": {"link_conditions": {}},
            "RB": {"port": 5012},
        }
        self.server_socket = Mock()
        self.packet = Packet(1, 2, 15, DATA, 17, b"payload")
        #start every test with fresh random generators
        network.link_randoms.clear()

    def set_condition(self, loss, delay, seed=1):
        self.config["RA"]["link_conditions"]["RB"] = {"loss": loss, "delay": delay, "seed": seed}

    def test_no_condition_sends_right_away(self):
        send_over_link("RA", self.config, self.server_socket, self.packet, "RB")

        data, address = self.server_socket.sendto.call_args.args
        self.assertEqual(decode(data), self.packet)
        self.assertEqual(address, ("127.0.0.1", 5012))

    def test_full_loss_drops_and_logs(self):
        self.set_condition(loss=1.0, delay=0)
        output = io.StringIO()

        with redirect_stdout(output):
            send_over_link("RA", self.config, self.server_socket, self.packet, "RB")

        self.server_socket.sendto.assert_not_called()
        self.assertIn("link loss RA->RB", output.getvalue())

    def test_delay_does_not_block(self):
        self.set_condition(loss=0.0, delay=0.2)

        start = time.monotonic()
        send_over_link("RA", self.config, self.server_socket, self.packet, "RB")

        #returns at once and nothing is sent yet
        self.assertLess(time.monotonic() - start, 0.1)
        self.server_socket.sendto.assert_not_called()

        #after the delay the timer has sent it
        time.sleep(0.4)
        self.server_socket.sendto.assert_called_once()

    def test_same_seed_gives_same_drops(self):
        self.set_condition(loss=0.5, delay=0, seed=7)

        def run_once():
            network.link_randoms.clear()
            self.server_socket.reset_mock()
            with redirect_stdout(io.StringIO()):
                for msg_id in range(20):
                    packet = Packet(1, 2, 15, DATA, msg_id, b"")
                    send_over_link("RA", self.config, self.server_socket, packet, "RB")
            #the ids that made it through
            return [decode(call.args[0]).msg_id for call in self.server_socket.sendto.call_args_list]

        first = run_once()
        self.assertEqual(first, run_once())
        #with 50% loss some packets get through and some don't
        self.assertTrue(0 < len(first) < 20)


if __name__ == "__main__":
    unittest.main()
