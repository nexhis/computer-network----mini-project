import struct
from dataclasses import dataclass

"""
PACKET FORMAT
- 10 byte header + payload
- src (2 bytes): who sent it
- dst (2 bytes): who it's for
- hop_limit (1 byte): goes down by 1 at each router, dropped at 0
- msg_type (1 byte): DATA, ECHO_REQUEST or ECHO_REPLY
- msg_id (4 bytes): id of the message, a reply uses the same id
- payload: the rest of the bytes
"""

# ! = network byte order, H = 2 bytes, B = 1 byte, I = 4 bytes
HEADER_FORMAT = "!HHBBI"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAX_PACKET_SIZE = 2048
MAX_PAYLOAD_SIZE = MAX_PACKET_SIZE - HEADER_SIZE
DEFAULT_HOP_LIMIT = 16

# message types, anything else is rejected
DATA = 1
ECHO_REQUEST = 2
ECHO_REPLY = 3
MSG_TYPES = {DATA, ECHO_REQUEST, ECHO_REPLY}


# the only error encode/decode give, so callers only need to catch this one
class PacketError(Exception):
    pass


@dataclass
class Packet:
    src: int
    dst: int
    hop_limit: int
    msg_type: int
    msg_id: int
    payload: bytes


"""
ENCODE
- Turns a Packet into bytes so we can send it
- Gives a PacketError if something is wrong with it
"""
def encode(packet):
    if len(packet.payload) > MAX_PAYLOAD_SIZE:
        raise PacketError(f"payload too big: {len(packet.payload)} bytes")

    if packet.msg_type not in MSG_TYPES:
        raise PacketError(f"unknown message type: {packet.msg_type}")

    # struct gives an error if a number doesn't fit its size (ex: src = 70000)
    try:
        header = struct.pack(HEADER_FORMAT, packet.src, packet.dst, packet.hop_limit, packet.msg_type, packet.msg_id)
    except struct.error as err:
        raise PacketError(f"field out of range: {err}")

    return header + packet.payload


"""
DECODE
- Turns the bytes we got back into a Packet
- Gives a PacketError if the packet is bad (too big, too short, wrong type, hop limit 0)
"""
def decode(data):
    if len(data) > MAX_PACKET_SIZE:
        raise PacketError(f"packet too big: {len(data)} bytes")

    # need at least the full header to read the fields
    if len(data) < HEADER_SIZE:
        raise PacketError(f"packet too short: {len(data)} bytes")

    # read the header fields from the first 10 bytes
    src, dst, hop_limit, msg_type, msg_id = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])

    if msg_type not in MSG_TYPES:
        raise PacketError(f"unknown message type: {msg_type}")

    # a packet with hop limit 0 should have been dropped already
    if hop_limit == 0:
        raise PacketError("hop limit is 0")

    # everything after the header is the payload
    return Packet(src, dst, hop_limit, msg_type, msg_id, data[HEADER_SIZE:])
