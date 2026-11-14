import struct
from dataclasses import dataclass

"""
PACKET FORMAT
- 10 byte header + payload
- src (2 bytes): who sent it
- dst (2 bytes): who it's for
- hop_limit (1 byte): goes down by 1 at each router, dropped at 0
- msg_type (1 byte): DATA, ECHO_REQUEST, ECHO_REPLY or ACK
- msg_id (4 bytes): id of the message, a reply uses the same id
- payload: the rest of the bytes
"""

#! = network byte order, H = 2 bytes, B = 1 byte, I = 4 bytes
HEADER_FORMAT = "!HHBBI"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAX_PACKET_SIZE = 2048
MAX_PAYLOAD_SIZE = MAX_PACKET_SIZE - HEADER_SIZE
DEFAULT_HOP_LIMIT = 16

#message types, anything else is rejected
DATA = 1
ECHO_REQUEST = 2
ECHO_REPLY = 3
ACK = 4
MSG_TYPES = {DATA, ECHO_REQUEST, ECHO_REPLY, ACK}


#the only error encode/decode give, so callers only need to catch this one
class PacketError(Exception):
    pass


"""
MAKE ID / SPLIT ID (for reliable transfer)
- msg_id is 4 bytes: first 2 bytes = run id, last 2 bytes = sequence number
- run_id and seq must be 0..65535
- An ACK uses the same msg_id as the DATA it acknowledges
"""
def make_id(run_id, seq):
    #a value over 65535 would spill into the other half of the id, so refuse it
    for name, value in (("run_id", run_id), ("seq", seq)):
        if not 0 <= value <= 0xFFFF:
            raise PacketError(f"{name} out of range: {value}")
    return (run_id << 16) | seq


def split_id(msg_id):
    #returns (run_id, seq)
    return msg_id >> 16, msg_id & 0xFFFF


"""
MAKE PAYLOAD / SPLIT PAYLOAD (for reliable transfer)
- A reliable DATA payload starts with a small text prefix "<seq>/<total>|"
  followed by the message bytes (ex: b"3/10|msg 3")
- total lets the receiver know which message is the last one (seq == total)
  so it can stay available for a bounded time afterwards
- The header stays the same 10 bytes, an ACK has an empty payload
- split_payload gives a PacketError if the prefix is missing or broken
"""
def make_payload(seq, total, body):
    return f"{seq}/{total}|".encode() + body


def split_payload(payload):
    #returns (seq, total, body)
    prefix, sep, body = payload.partition(b"|")
    if not sep:
        raise PacketError("reliable payload has no seq/total prefix")
    try:
        seq_text, total_text = prefix.decode("ascii").split("/")
        seq, total = int(seq_text), int(total_text)
    except (UnicodeDecodeError, ValueError):
        raise PacketError(f"bad seq/total prefix: {prefix!r}")
    if not 1 <= seq <= total:
        raise PacketError(f"seq {seq} not in 1..{total}")
    return seq, total, body


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

    #struct gives an error if a number doesn't fit its size (ex: src = 70000)
    try:
        header = struct.pack(HEADER_FORMAT, packet.src, packet.dst, packet.hop_limit, packet.msg_type, packet.msg_id)
    except struct.error as err:
        raise PacketError(f"field out of range: {err}")

    return header + packet.payload


"""
DECODE
- Turns the bytes we got back into a Packet
- Gives a PacketError if the packet is bad (too big, too short, or wrong type)
"""
def decode(data):
    if len(data) > MAX_PACKET_SIZE:
        raise PacketError(f"packet too big: {len(data)} bytes")

    #need at least the full header to read the fields
    if len(data) < HEADER_SIZE:
        raise PacketError(f"packet too short: {len(data)} bytes")

    #read the header fields from the first 10 bytes
    src, dst, hop_limit, msg_type, msg_id = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])

    if msg_type not in MSG_TYPES:
        raise PacketError(f"unknown message type: {msg_type}")



    #everything after the header is the payload
    return Packet(src, dst, hop_limit, msg_type, msg_id, data[HEADER_SIZE:])
