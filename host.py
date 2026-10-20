import argparse
import socket
import time

from network import start
from packet import (
    DEFAULT_HOP_LIMIT,
    ECHO_REPLY,
    ECHO_REQUEST,
    MAX_PACKET_SIZE,
    Packet,
    PacketError,
    decode,
    encode,
)

#how long a host waits for an echo reply before giving up (no retransmission)
RESPONSE_TIMEOUT = 2.0

def send_to_router(device_name, config, server_socket, packet):
    neighbors = config[device_name]["neighbors"]
    if not neighbors or neighbors[0] not in config:
        print(f"{device_name} DROP id={packet.msg_id}: invalid next hop")
        return False

    next_hop = neighbors[0]
    address = ("127.0.0.1", config[next_hop]["port"])
    try:
        server_socket.sendto(encode(packet), address)
    except OSError as err:
        print(f"{device_name} DROP id={packet.msg_id}: invalid next hop {next_hop!r}: {err}")
        return False
    return True

def handle_packet(device_name, config, server_socket, packet):
    host_address = config[device_name]["vaddr"]
    if packet.dst != host_address:
        print(
            f"{device_name} DROP id={packet.msg_id} dst={packet.dst}: "
            "packet is not addressed to this host"
        )
        return

    text = packet.payload.decode(errors="replace")
    print(
        f"{device_name} RECV id={packet.msg_id} type={packet.msg_type} "
        f"src={packet.src} dst={packet.dst} hop={packet.hop_limit} payload='{text}'"
    )

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
        print(f"{device_name} DROP from {address}: {err}")
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
            print(f"{device_name} TIMEOUT id={msg_id} dst={destination} after {timeout:g}s")
            return

        server_socket.settimeout(remaining)
        try:
            packet = receive_packet(device_name, config, server_socket)
        except socket.timeout:
            print(f"{device_name} TIMEOUT id={msg_id} dst={destination} after {timeout:g}s")
            return

        if (
            packet is not None
            and packet.dst == source
            and packet.src == destination
            and packet.msg_type == ECHO_REPLY
            and packet.msg_id == msg_id
        ):
            print(f"{device_name} OK id={msg_id} matching reply from {destination}")
            return


def main():
    parser = argparse.ArgumentParser(description="Run a mini-internet host.")
    parser.add_argument("device_name")
    parser.add_argument("--send-to", type=int, help="send an echo request to this virtual address")
    parser.add_argument("--message", default="ping")
    args = parser.parse_args()

    device_name, config, server_socket = start(args.device_name, "host")
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
