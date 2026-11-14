import socket
import time

from host import receive_packet, send_to_router
from logger import log_event
from packet import ACK, DATA, DEFAULT_HOP_LIMIT, Packet, make_id, make_payload, split_id

"""
RELIABLE TRANSFER - SENDER SIDE (Track B)
- send_reliable: stop-and-wait, at most one unacknowledged message outstanding

Sender states (stop-and-wait):
  SEND(seq)  -> send DATA seq, start the timer          -> WAIT_ACK
  WAIT_ACK   -> matching ACK for seq                    -> SEND(seq+1), or DONE after the last seq
  WAIT_ACK   -> timer runs out, retries left            -> RETX (send the same DATA again) -> WAIT_ACK
  WAIT_ACK   -> timer runs out, no retries left         -> FAILED (explicit, bounded failure)
  WAIT_ACK   -> old/duplicate ACK or other packet       -> ignored, keep waiting (timer is NOT restarted)
"""

#defaults, all can be changed from the command line in host.py
DEFAULT_TIMEOUT = 1.0      #seconds to wait for an ACK before retransmitting
DEFAULT_MAX_RETRIES = 5    #retransmissions allowed per message before giving up
DEFAULT_COUNT = 10         #how many generated messages to send


"""
GENERATE MESSAGES
- Makes the finite message set used for a run: b"msg 1", b"msg 2", ...
- The same count always gives the same messages
"""
def generate_messages(count):
    return [f"msg {i}".encode() for i in range(1, count + 1)]


"""
MAKE RUN ID
- A 16 bit run id taken from the clock, so two runs don't share ids
- The receiver uses it to tell a new transfer from an old one
"""
def make_run_id():
    return time.time_ns() // 1_000_000 & 0xFFFF


"""
MAKE DATA PACKET
- Builds the DATA packet for one message
- msg_id = run id + seq, payload = "<seq>/<total>|" + message
"""
def make_data_packet(source, destination, run_id, seq, total, body):
    return Packet(
        src=source,
        dst=destination,
        hop_limit=DEFAULT_HOP_LIMIT,
        msg_type=DATA,
        msg_id=make_id(run_id, seq),
        payload=make_payload(seq, total, body),
    )


"""
IS MATCHING ACK
- True only if the packet is the ACK for exactly this DATA packet:
  type ACK, from the destination, to us, and the same msg_id (same run id and seq)
"""
def is_matching_ack(packet, data_packet):
    return (
        packet is not None
        and packet.msg_type == ACK
        and packet.src == data_packet.dst
        and packet.dst == data_packet.src
        and packet.msg_id == data_packet.msg_id
    )


"""
WAIT FOR ACK
- Waits up to `timeout` seconds for the ACK of data_packet
- Returns True when the matching ACK arrives, False when the timer runs out
- An ACK for an older seq of this run (ex: a late duplicate) is logged as IGNORE
- The deadline is fixed when we start waiting, so other packets can't keep us waiting forever
"""
def wait_for_ack(device_name, config, server_socket, data_packet, timeout):
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False

        server_socket.settimeout(remaining)
        try:
            packet = receive_packet(device_name, config, server_socket)
        except socket.timeout:
            return False

        if is_matching_ack(packet, data_packet):
            return True

        if packet is not None and packet.msg_type == ACK:
            log_event(device_name, "IGNORE", packet, note=f"ack {split_id(packet.msg_id)} is not for {split_id(data_packet.msg_id)}")


"""
SEND RELIABLE (stop-and-wait)
- Sends the messages one at a time, in order, seq 1..N
- After each DATA it waits for the matching ACK before sending the next one
- No ACK in time -> RETX, up to max_retries times per message
- Still no ACK after that -> FAIL, the run stops (no endless wait)
- Returns a stats dict: status (DONE/FAILED), messages, acked, sent, retransmissions, elapsed
"""
def send_reliable(device_name, config, server_socket, destination, messages,
                  run_id, timeout=DEFAULT_TIMEOUT, max_retries=DEFAULT_MAX_RETRIES):
    source = config[device_name]["vaddr"]
    total = len(messages)
    stats = {"run_id": run_id, "status": "DONE", "messages": total,
             "acked": 0, "sent": 0, "retransmissions": 0, "elapsed": 0.0}
    start_time = time.monotonic()

    for seq, body in enumerate(messages, start=1):
        data_packet = make_data_packet(source, destination, run_id, seq, total, body)
        retries = 0

        while True:
            if retries > 0:
                stats["retransmissions"] += 1
                log_event(device_name, "RETX", data_packet, note=f"seq={seq} retry {retries}/{max_retries}")
            send_to_router(device_name, config, server_socket, data_packet)
            stats["sent"] += 1

            if wait_for_ack(device_name, config, server_socket, data_packet, timeout):
                stats["acked"] += 1
                log_event(device_name, "OK", data_packet, note=f"seq={seq}/{total} acknowledged")
                break

            log_event(device_name, "TIMEOUT", data_packet, note=f"seq={seq} no ack after {timeout:g}s")
            retries += 1
            if retries > max_retries:
                stats["status"] = "FAILED"
                stats["elapsed"] = time.monotonic() - start_time
                log_event(device_name, "FAIL", data_packet,
                          note=f"seq={seq} unacknowledged after {max_retries} retransmissions, giving up")
                return stats

    stats["elapsed"] = time.monotonic() - start_time
    log_event(device_name, "DONE", note=f"run_id={run_id} all {total} messages acknowledged")
    return stats


"""
SUMMARY LINE
- One line with the stats of a run, logged as SUMMARY so it ends up in the log file too
"""
def summary_line(stats):
    return (f"run_id={stats['run_id']} status={stats['status']} "
            f"messages={stats['messages']} acked={stats['acked']} sent={stats['sent']} "
            f"retransmissions={stats['retransmissions']} elapsed={stats['elapsed']:.3f}s")
