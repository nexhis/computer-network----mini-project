import argparse
import socket
import time

from logger import log_event
from network import send_over_link, start
from packet import (
    DEFAULT_HOP_LIMIT,
    ECHO_REPLY,
    ECHO_REQUEST,
    MAX_PACKET_SIZE,
    Packet,
    PacketError,
    decode,
)

#how long a host waits for an echo reply before giving up (no retransmission)
RESPONSE_TIMEOUT = 2.0

def send_to_router(device_name, config, server_socket, packet):
    neighbors = config[device_name]["neighbors"]
    if not neighbors or neighbors[0] not in config:
        log_event(device_name, "DROP", packet, note="invalid next hop")
        return False

    next_hop = neighbors[0]

    #log SEND first, so a link loss DROP from send_over_link comes after it in the log
    log_event(device_name, "SEND", packet, next_hop)
    try:
        send_over_link(device_name, config, server_socket, packet, next_hop)
    except OSError as err:
        log_event(device_name, "DROP", packet, next_hop, note=f"invalid next hop {next_hop!r}: {err}")
        return False
    return True

def handle_packet(device_name, config, server_socket, packet):
    host_address = config[device_name]["vaddr"]
    if packet.dst != host_address:
        log_event(device_name, "DROP", packet, note="packet is not addressed to this host")
        return

    text = packet.payload.decode(errors="replace")
    log_event(device_name, "RECV", packet, note=f"payload='{text}'")

    if packet.msg_type == ECHO_REQUEST:
        reply = Packet(
            src=host_address,
            dst=packet.src,
            hop_limit=DEFAULT_HOP_LIMIT,
            msg_type=ECHO_REPLY,
            msg_id=packet.msg_id,
            payload=packet.payload,
        )
        send_to_router(device_name, config, server_socket, reply)


def receive_packet(device_name, config, server_socket):
    data, address = server_socket.recvfrom(MAX_PACKET_SIZE + 1)
    try:
        packet = decode(data)
    except PacketError as err:
        log_event(device_name, "DROP", note=f"{err} from {address}")
        return None
    handle_packet(device_name, config, server_socket, packet)
    return packet


def send_echo(device_name, config, server_socket, destination, message):
    source = config[device_name]["vaddr"]
    msg_id = time.time_ns() & 0xFFFFFFFF
    request = Packet(
        src=source,
        dst=destination,
        hop_limit=DEFAULT_HOP_LIMIT,
        msg_type=ECHO_REQUEST,
        msg_id=msg_id,
        payload=message.encode(),
    )
    if not send_to_router(device_name, config, server_socket, request):
        return

    timeout = RESPONSE_TIMEOUT
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            log_event(device_name, "TIMEOUT", request, note=f"no reply after {timeout:g}s")
            return

        server_socket.settimeout(remaining)
        try:
            packet = receive_packet(device_name, config, server_socket)
        except socket.timeout:
            log_event(device_name, "TIMEOUT", request, note=f"no reply after {timeout:g}s")
            return

        if (
            packet is not None
            and packet.dst == source
            and packet.src == destination
            and packet.msg_type == ECHO_REPLY
            and packet.msg_id == msg_id
        ):
            log_event(device_name, "OK", packet, note=f"matching reply from {destination}")
            return


def main():
    parser = argparse.ArgumentParser(description="Run a mini-internet host.")
    parser.add_argument("device_name")
    parser.add_argument("--send-to", type=int, help="send an echo request to this virtual address")
    parser.add_argument("--message", default="ping")
    parser.add_argument("--run", default="run", help="run name, logs go to logs/<run>/")
    args = parser.parse_args()

    device_name, config, server_socket = start(args.device_name, "host", args.run)
    if args.send_to is not None:
        known_addresses = {info["vaddr"] for info in config.values()}
        if args.send_to not in known_addresses:
            parser.error(f"unknown destination virtual address: {args.send_to}")
        send_echo(
            device_name,
            config,
            server_socket,
            args.send_to,
            args.message,
        )
        return

    while True:
        receive_packet(device_name, config, server_socket)


if __name__ == "__main__":
    main()
