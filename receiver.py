import argparse
import socket
import time

from host import send_to_router
from logger import log_event
from network import start
from packet import ACK, DATA, DEFAULT_HOP_LIMIT, MAX_PACKET_SIZE, Packet, PacketError, decode, split_id, split_payload

"""
RECEIVER FOR STOP-AND-WAIT (Track B)
- States:
  - EXPECTING n: waiting for message seq n
  - WAIT_AFTER_LAST: the last message was delivered, stay up a few seconds to ACK a resent last message
    (same idea as TIME_WAIT in TCP)
  - CLOSED: the wait is over, the receiver stops
- msg_id = run id + seq (see make_id in packet.py), payload = "<seq>/<total>|<text>" (see make_payload)
- seq goes 1..total, the last message is seq == total
"""

#seconds the receiver stays up after the last message (should be >= sender timeout x retries)
#sender defaults are 1.0s x 5 retries = 5s, plus 1s margin
WAIT_AFTER_LAST = 6.0


"""
NEW STATE
- Everything the receiver needs to remember during a run
"""
def new_state(drop_ack_seq=None):
    return {
        "run_id": None,
        "expected": 1,
        "delivered": [],
        "drop_ack_seq": drop_ack_seq,
        "ack_dropped": False,
    }


"""
SEND ACK
- Sends an ACK with the same msg_id as the DATA packet
- If --drop-ack-seq matches, the first ACK for that seq is not sent (for the lost ACK test)
"""
def send_ack(device_name, config, server_socket, state, data_packet, seq, is_last):
    ack = Packet(
        src=data_packet.dst,
        dst=data_packet.src,
        hop_limit=DEFAULT_HOP_LIMIT,
        msg_type=ACK,
        msg_id=data_packet.msg_id,
        payload=b"",
    )

    drop = state["drop_ack_seq"]
    if not state["ack_dropped"] and (drop == str(seq) or (drop == "last" and is_last)):
        state["ack_dropped"] = True
        log_event(device_name, "DROP", ack, note=f"ACK for seq={seq} dropped on purpose")
        return

    send_to_router(device_name, config, server_socket, ack)


"""
HANDLE DATA
- seq == expected: deliver it, ACK it, wait for the next one
- seq < expected: duplicate (our ACK got lost), ACK it again but don't deliver
- seq > expected: should not happen with stop-and-wait, drop it
- Returns True when the last message was just delivered
"""
def handle_data(device_name, config, server_socket, state, packet):
    run_id, seq = split_id(packet.msg_id)

    #payload is "<seq>/<total>|<text>", split_payload is in packet.py
    try:
        _, total, body = split_payload(packet.payload)
    except PacketError as err:
        log_event(device_name, "DROP", packet, note=f"bad payload: {err}")
        return False
    text = body.decode(errors="replace")

    #a new run starts with seq 1, packets from other runs are ignored
    if run_id != state["run_id"]:
        if seq != 1:
            log_event(device_name, "DROP", packet, note=f"unknown run={run_id}")
            return False
        state["run_id"] = run_id
        state["expected"] = 1
        state["delivered"] = []

    is_last = seq == total

    if seq == state["expected"]:
        state["delivered"].append(text)
        state["expected"] += 1
        log_event(device_name, "DELIVER", packet, note=f"run={run_id} seq={seq} text='{text}'")
        send_ack(device_name, config, server_socket, state, packet, seq, is_last)
        return is_last

    if seq < state["expected"]:
        log_event(device_name, "DUP", packet, note=f"run={run_id} seq={seq} sending ACK again")
        send_ack(device_name, config, server_socket, state, packet, seq, is_last)
        return False

    log_event(device_name, "DROP", packet, note=f"out of order seq={seq}, expected {state['expected']}")
    return False


"""
RECEIVE LOOP
- Waits for DATA packets and handles them
- After the last message: WAIT_AFTER_LAST seconds, then CLOSED
"""
def receive_loop(device_name, config, server_socket, state, wait_time=WAIT_AFTER_LAST):
    my_address = config[device_name]["vaddr"]
    wait_end = None

    while True:
        #after the last message we only wait until wait_end
        if wait_end is not None:
            remaining = wait_end - time.monotonic()
            if remaining <= 0:
                break
            server_socket.settimeout(remaining)

        try:
            data, address = server_socket.recvfrom(MAX_PACKET_SIZE + 1)
        except socket.timeout:
            #only happens after the last message (before that there is no timeout)
            break

        try:
            packet = decode(data)
        except PacketError as err:
            log_event(device_name, "DROP", note=f"{err} from {address}")
            continue

        if packet.dst != my_address or packet.msg_type != DATA:
            log_event(device_name, "DROP", packet, note="not a DATA packet for this host")
            continue

        last_delivered = handle_data(device_name, config, server_socket, state, packet)
        if last_delivered and wait_end is None:
            wait_end = time.monotonic() + wait_time
            log_event(device_name, "WAIT_AFTER_LAST", note=f"last message delivered, staying up {wait_time:g}s")

    log_event(device_name, "CLOSED", note=f"delivered {len(state['delivered'])} messages")


def main():
    parser = argparse.ArgumentParser(description="Stop-and-wait receiver.")
    parser.add_argument("device_name")
    parser.add_argument("--drop-ack-seq", help="don't send the first ACK for this seq (a number or 'last')")
    parser.add_argument("--run", default="run", help="run name, logs go to logs/<run>/")
    args = parser.parse_args()

    device_name, config, server_socket = start(args.device_name, "host", args.run)
    state = new_state(args.drop_ack_seq)
    receive_loop(device_name, config, server_socket, state)


if __name__ == "__main__":
    main()
