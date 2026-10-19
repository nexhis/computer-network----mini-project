import argparse

from network import start
from packet import MAX_PACKET_SIZE, Packet, PacketError, decode, encode


def forward_packet(device_name, config, packet, server_socket):
    router = config[device_name]

    if packet.hop_limit <= 1:
        print(
            f"{device_name} DROP id={packet.msg_id} dst={packet.dst}: "
            f"exhausted hop limit ({packet.hop_limit})"
        )
        return

    next_hop = router.get("routes", {}).get(str(packet.dst))
    if next_hop is None:
        print(f"{device_name} DROP id={packet.msg_id} dst={packet.dst}: unknown destination")
        return

    if next_hop not in router["neighbors"] or next_hop not in config:
        print(
            f"{device_name} DROP id={packet.msg_id} dst={packet.dst}: "
            f"invalid next hop {next_hop!r}"
        )
        return

    forwarded = Packet(
        src=packet.src,
        dst=packet.dst,
        hop_limit=packet.hop_limit - 1,
        msg_type=packet.msg_type,
        msg_id=packet.msg_id,
        payload=packet.payload,
    )
    address = ("127.0.0.1", config[next_hop]["port"])

    try:
        server_socket.sendto(encode(forwarded), address)
    except OSError as err:
        print(
            f"{device_name} DROP id={packet.msg_id} dst={packet.dst}: "
            f"invalid next hop {next_hop!r}: {err}"
        )
        return

    print(
        f"{device_name} FWD id={packet.msg_id} dst={packet.dst} "
        f"next_hop={next_hop} hop={forwarded.hop_limit}"
    )


def run_router(device_name):
    device_name, config, server_socket = start(device_name, "router")

    while True:
        data, address = server_socket.recvfrom(MAX_PACKET_SIZE + 1)
        try:
            packet = decode(data)
        except PacketError as err:
            print(f"{device_name} DROP from {address}: {err}")
            continue

        forward_packet(device_name, config, packet, server_socket)


def main():
    parser = argparse.ArgumentParser(description="Run a mini-internet router.")
    parser.add_argument("device_name")
    args = parser.parse_args()
    run_router(args.device_name)


if __name__ == "__main__":
    main()
