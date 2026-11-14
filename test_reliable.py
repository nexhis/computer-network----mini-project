import socket
import unittest
from unittest import mock

import reliable
from packet import ACK, DEFAULT_HOP_LIMIT, Packet, make_id, split_id, split_payload

"""
TESTS FOR reliable.py (sender side)
- The real network is replaced by FakeNetwork, which plays a simple receiver:
  it delivers each new seq once and in order, and ACKs every DATA it gets (duplicates too)
- Packets can be dropped on purpose by their send number (DATA) or by seq (ACK)
- No real sockets or sleeping: a timeout happens right away when no ACK is waiting
"""

SENDER = 1
RECEIVER = 2
CONFIG = {"H1": {"type": "host", "vaddr": SENDER, "port": 0, "neighbors": ["RA"]}}


"""
FAKE NETWORK
- send() stands in for host.send_to_router, receive() for host.receive_packet
- drop_data_sends: which DATA sends to lose (1 = the first DATA sent, 2 = the second, ...)
- drop_ack_seqs: for which seqs to lose the ACK once (the first ACK for that seq)
- drop_all: lose every DATA, as if the destination was unreachable
"""
class FakeNetwork:
    def __init__(self, drop_data_sends=(), drop_ack_seqs=(), drop_all=False):
        self.drop_data_sends = set(drop_data_sends)
        self.drop_ack_seqs = set(drop_ack_seqs)
        self.drop_all = drop_all
        self.sent = []          #every DATA the sender sent, in order
        self.delivered = []     #message bodies the fake receiver delivered
        self.expected_seq = 1
        self.waiting_acks = []

    def send(self, device_name, config, server_socket, packet):
        self.sent.append(packet)
        if self.drop_all or len(self.sent) in self.drop_data_sends:
            return True

        seq, total, body = split_payload(packet.payload)
        if seq == self.expected_seq:
            self.delivered.append(body)
            self.expected_seq += 1

        if seq in self.drop_ack_seqs:
            self.drop_ack_seqs.discard(seq)
            return True
        self.waiting_acks.append(Packet(RECEIVER, SENDER, DEFAULT_HOP_LIMIT, ACK, packet.msg_id, b""))
        return True

    def receive(self, device_name, config, server_socket):
        if not self.waiting_acks:
            raise socket.timeout()
        return self.waiting_acks.pop(0)


"""
RUN RELIABLE
- Runs the sender against a FakeNetwork
"""
def run_reliable(network, count=5, max_retries=3):
    with mock.patch.object(reliable, "send_to_router", network.send), \
         mock.patch.object(reliable, "receive_packet", network.receive):
        return reliable.send_reliable("H1", CONFIG, mock.Mock(), RECEIVER,
                                      reliable.generate_messages(count), run_id=7,
                                      timeout=0.01, max_retries=max_retries)


class TestStopAndWait(unittest.TestCase):

    def test_no_loss_in_order_no_duplicates(self):
        network = FakeNetwork()
        stats = run_reliable(network)
        self.assertEqual(stats["status"], "DONE")
        self.assertEqual(network.delivered, reliable.generate_messages(5))
        self.assertEqual(stats["retransmissions"], 0)
        self.assertEqual(stats["sent"], 5)
        self.assertEqual([split_id(p.msg_id) for p in network.sent], [(7, s) for s in range(1, 6)])

    def test_one_dropped_data_is_retransmitted(self):
        network = FakeNetwork(drop_data_sends={3})   #DATA seq 3 lost the first time
        stats = run_reliable(network)
        self.assertEqual(stats["status"], "DONE")
        self.assertEqual(network.delivered, reliable.generate_messages(5))
        self.assertEqual(stats["retransmissions"], 1)
        self.assertEqual(stats["sent"], 6)

    def test_dropped_final_ack_still_completes(self):
        network = FakeNetwork(drop_ack_seqs={5})     #ACK of the last message lost once
        stats = run_reliable(network)
        self.assertEqual(stats["status"], "DONE")
        #the receiver got seq 5 twice but delivered it only once
        self.assertEqual(network.delivered, reliable.generate_messages(5))
        self.assertEqual(stats["retransmissions"], 1)
        self.assertEqual(stats["acked"], 5)

    def test_unreachable_destination_fails_bounded(self):
        network = FakeNetwork(drop_all=True)
        stats = run_reliable(network, max_retries=3)
        self.assertEqual(stats["status"], "FAILED")
        #first send + 3 retransmissions of seq 1, then it stops
        self.assertEqual(stats["sent"], 4)
        self.assertEqual(stats["retransmissions"], 3)
        self.assertEqual(stats["acked"], 0)

    def test_old_ack_is_ignored(self):
        network = FakeNetwork()
        #a late duplicate ACK for seq 1 is waiting when the sender waits for seq 2
        stale = Packet(RECEIVER, SENDER, DEFAULT_HOP_LIMIT, ACK, make_id(7, 1), b"")
        original_send = network.send

        def send_and_inject(*args):
            packet = args[3]
            if split_id(packet.msg_id)[1] == 2:
                network.waiting_acks.append(stale)
            return original_send(*args)

        network.send = send_and_inject
        stats = run_reliable(network, count=3)
        self.assertEqual(stats["status"], "DONE")
        self.assertEqual(stats["retransmissions"], 0)


if __name__ == "__main__":
    unittest.main()
