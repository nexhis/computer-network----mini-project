import socket
import unittest
from unittest.mock import Mock

from packet import ACK, DATA, DEFAULT_HOP_LIMIT, Packet, decode, encode, make_id, make_payload, split_id
from receiver import handle_data, new_state, receive_loop

"""
TESTS FOR receiver.py
- A Mock socket is used instead of a real one, every ACK the receiver sends ends up in sendto
"""

#H2 sends its ACKs to RD
CONFIG = {
    "H2": {"vaddr": 2, "neighbors": ["RD"]},
    "RD": {"port": 5014},
}


#DATA packet from H1 to H2, built like the sender does (payload "<seq>/<total>|msg <seq>")
def data_packet(seq, total, run_id=7):
    return Packet(1, 2, DEFAULT_HOP_LIMIT, DATA, make_id(run_id, seq), make_payload(seq, total, f"msg {seq}".encode()))


#seq numbers of all the ACKs that were sent
def acked_seqs(server_socket):
    seqs = []
    for call in server_socket.sendto.call_args_list:
        ack = decode(call.args[0])
        if ack.msg_type == ACK:
            seqs.append(split_id(ack.msg_id)[1])
    return seqs


class TestHandleData(unittest.TestCase):

    def setUp(self):
        self.server_socket = Mock()

    def receive(self, state, packet):
        return handle_data("H2", CONFIG, self.server_socket, state, packet)

    def test_in_order_no_loss(self):
        state = new_state()
        for seq in range(1, 4):
            self.receive(state, data_packet(seq, 3))
        self.assertEqual(state["delivered"], ["msg 1", "msg 2", "msg 3"])
        self.assertEqual(acked_seqs(self.server_socket), [1, 2, 3])

    def test_duplicate_is_acked_but_not_delivered(self):
        state = new_state()
        self.receive(state, data_packet(1, 3))
        self.receive(state, data_packet(1, 3))
        self.assertEqual(state["delivered"], ["msg 1"])
        self.assertEqual(acked_seqs(self.server_socket), [1, 1])

    def test_out_of_order_is_dropped(self):
        state = new_state()
        self.receive(state, data_packet(1, 3))
        self.receive(state, data_packet(3, 3))
        self.assertEqual(state["delivered"], ["msg 1"])
        self.assertEqual(acked_seqs(self.server_socket), [1])

    def test_other_run_is_ignored(self):
        state = new_state()
        self.receive(state, data_packet(1, 3, run_id=7))
        self.receive(state, data_packet(2, 3, run_id=8))
        self.assertEqual(state["delivered"], ["msg 1"])

    def test_returns_true_only_for_last(self):
        state = new_state()
        self.assertFalse(self.receive(state, data_packet(1, 2)))
        self.assertTrue(self.receive(state, data_packet(2, 2)))

    def test_dropped_last_ack_is_sent_for_the_resent_last(self):
        state = new_state(drop_ack_seq="last")
        self.receive(state, data_packet(1, 2))
        self.receive(state, data_packet(2, 2))
        #first ACK for seq 2 was dropped on purpose
        self.assertEqual(acked_seqs(self.server_socket), [1])
        #sender times out and sends seq 2 again, now it gets its ACK
        self.receive(state, data_packet(2, 2))
        self.assertEqual(acked_seqs(self.server_socket), [1, 2])
        self.assertEqual(state["delivered"], ["msg 1", "msg 2"])


class TestReceiveLoop(unittest.TestCase):

    def test_waits_after_last_then_closes(self):
        server_socket = Mock()
        address = ("127.0.0.1", 5014)
        #last message, then the same last message again, then nothing more comes
        server_socket.recvfrom.side_effect = [
            (encode(data_packet(1, 1)), address),
            (encode(data_packet(1, 1)), address),
            socket.timeout(),
        ]
        state = new_state(drop_ack_seq="last")

        receive_loop("H2", CONFIG, server_socket, state, wait_time=0.5)

        #the loop ended by itself (bounded), the resent last message got its ACK
        self.assertEqual(state["delivered"], ["msg 1"])
        self.assertEqual(acked_seqs(server_socket), [1])
        server_socket.settimeout.assert_called()


if __name__ == "__main__":
    unittest.main()
