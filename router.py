import argparse

from logger import log_event
from network import send_over_link, start
from packet import MAX_PACKET_SIZE, Packet, PacketError, decode


def forward_packet(device_name, config, packet, server_socket):
    router = config[device_name]

    if packet.hop_limit <= 1:
        log_event(device_name, "DROP", packet, note=f"exhausted hop limit ({packet.hop_limit})")
        return

    next_hop = router.get("routes", {}).get(str(packet.dst))
    if next_hop is None:
        log_event(device_name, "DROP", packet, note="unknown destination")
        return

    if next_hop not in router["neighbors"] or next_hop not in config:
        log_event(device_name, "DROP", packet, note=f"invalid next hop {next_hop!r}")
        return

    forwarded = Packet(
        src=packet.src,
        dst=packet.dst,
        hop_limit=packet.hop_limit - 1,
        msg_type=packet.msg_type,
        msg_id=packet.msg_id,
        payload=packet.payload,
    )

    #log FWD first, so a link loss DROP from send_over_link comes after it in the log
    log_event(device_name, "FWD", forwarded, next_hop)

    try:
        send_over_link(device_name, config, server_socket, forwarded, next_hop)
    except OSError as err:
        log_event(device_name, "DROP", forwarded, next_hop, note=f"invalid next hop {next_hop!r}: {err}")


def run_router(device_name, run):
    device_name, config, server_socket = start(device_name, "router", run)

    while True:
        data, address = server_socket.recvfrom(MAX_PACKET_SIZE + 1)
        try:
            packet = decode(data)
        except PacketError as err:
            log_event(device_name, "DROP", note=f"{err} from {address}")
            continue

        log_event(device_name, "RECV", packet)
        forward_packet(device_name, config, packet, server_socket)


def main():
    parser = argparse.ArgumentParser(description="Run a mini-internet router.")
    parser.add_argument("device_name")
    parser.add_argument("--run", default="run", help="run name, logs go to logs/<run>/")
    args = parser.parse_args()
    run_router(args.device_name, args.run)


if __name__ == "__main__":
    main()
