from network import start
from packet import decode, PacketError, MAX_PACKET_SIZE
import sys

"""
- This module is the entry point to starting a router type device. Start this server with the command python3 router.py device_name
- Calls start() function from network.py and takes the three values (tuple) device_name, config object, and the server_socket object from start()
- Runs forever until inturrupted ready to recive packets
- Every packet is decoded with decode() from packet.py
- Good packets are printed as RECV, bad packets are printed as DROP and the router keeps running
- No forwarding yet, the router only prints what it gets
"""

device_name, config, server_socket = start(sys.argv[1], "router")

while True:
    #ask for 1 extra byte so we can tell if a packet is too big
    data, address = server_socket.recvfrom(MAX_PACKET_SIZE + 1)

    #a bad packet only gets a DROP message, it doesn't crash the router
    try:
        packet = decode(data)
    except PacketError as err:
        print(f"{device_name} DROP from {address}: {err}")
        continue

    #payload is bytes, turn it into text just for printing
    text = packet.payload.decode(errors="replace")
    print(f"{device_name} RECV id={packet.msg_id} type={packet.msg_type} src={packet.src} dst={packet.dst} hop={packet.hop_limit} payload='{text}'")
