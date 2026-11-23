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


def send_echo(device_name, config, server_socket, destination, message, timeout):
    source = config[device_name]["vaddr"]
    msg_id = time.time_ns() & 0xFFFFFFFF
    sent_at = time.monotonic()
    request = Packet(
        src=source,
        dst=destination,
        hop_limit=DEFAULT_HOP_LIMIT,
        msg_type=ECHO_REQUEST,
        msg_id=msg_id,
        payload=message.encode(),
    )
    if not send_to_router(device_name, config, server_socket, request):
        return None

    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print(f"{device_name} TIMEOUT id={msg_id} dst={destination} after {timeout:g}s")
            return None

        server_socket.settimeout(remaining)
        try:
            packet = receive_packet(device_name, config, server_socket)
        except socket.timeout:
            print(f"{device_name} TIMEOUT id={msg_id} dst={destination} after {timeout:g}s")
            return None

        if (
            packet is not None
            and packet.dst == source
            and packet.src == destination
            and packet.msg_type == ECHO_REPLY
            and packet.msg_id == msg_id
        ):
            rtt_ms = (time.monotonic() - sent_at) * 1000
            payload_matches = packet.payload == message.encode()
            print(
                f"{device_name} REPLY id={msg_id} src={packet.src} "
                f"dst={packet.dst} rtt={rtt_ms:.3f}ms "
                f"payload={'MATCH' if payload_matches else 'MISMATCH'}"
            )
            return rtt_ms if payload_matches else None


def run_comparison(
    device_name,
    config,
    server_socket,
    destination,
    message,
    timeout,
    count,
    interval,
    route_label,
):
    samples = []

    for attempt in range(1, count + 1):
        print(
            f"{device_name} TEST route={route_label} attempt={attempt}/{count} "
            f"dst={destination}"
        )
        result = send_echo(
            device_name,
            config,
            server_socket,
            destination,
            message,
            timeout,
        )
        if result is not None:
            samples.append(result)

        if attempt < count:
            time.sleep(interval)

    sent = count
    received = len(samples)
    lost = sent - received
    success_rate = (received / sent * 100) if sent else 0.0
    loss_rate = (lost / sent * 100) if sent else 0.0
    average_rtt = sum(samples) / received if received else None
    minimum_rtt = min(samples) if received else None
    maximum_rtt = max(samples) if received else None

    average_text = f"{average_rtt:.3f}ms" if average_rtt is not None else "N/A"
    minimum_text = f"{minimum_rtt:.3f}ms" if minimum_rtt is not None else "N/A"
    maximum_text = f"{maximum_rtt:.3f}ms" if maximum_rtt is not None else "N/A"
    print(
        f"{device_name} SUMMARY route={route_label} sent={sent} received={received} "
        f"lost={lost} success={success_rate:.1f}% loss={loss_rate:.1f}% "
        f"min={minimum_text} avg={average_text} max={maximum_text}"
    )


def main():
    parser = argparse.ArgumentParser(description="Run a mini-internet host.")
    parser.add_argument("device_name")
    parser.add_argument("--send-to", type=int, help="send an echo request to this virtual address")
    parser.add_argument("--message", default="ping")
    parser.add_argument("--timeout", type=float, default=3.0, help="reply timeout in seconds")
    parser.add_argument("--count", type=int, default=1, help="number of echo requests")
    parser.add_argument("--interval", type=float, default=0.0, help="seconds between echo requests")
    parser.add_argument("--route-label", default="configured", help="label for the active route")
    args = parser.parse_args()

    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if args.count <= 0:
        parser.error("--count must be greater than zero")
    if args.interval < 0:
        parser.error("--interval cannot be negative")

    device_name, config, server_socket = start(args.device_name, "host")
    if args.send_to is not None:
        known_addresses = {info["vaddr"] for info in config.values()}
        if args.send_to not in known_addresses:
            parser.error(f"unknown destination virtual address: {args.send_to}")
        if args.count == 1:
            send_echo(
                device_name,
                config,
                server_socket,
                args.send_to,
                args.message,
                args.timeout,
            )
        else:
            run_comparison(
                device_name,
                config,
                server_socket,
                args.send_to,
                args.message,
                args.timeout,
                args.count,
                args.interval,
                args.route_label,
            )
        return

    while True:
        receive_packet(device_name, config, server_socket)


if __name__ == "__main__":
    main()
