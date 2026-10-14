START THIS PROJECT WITH EITHER: 
- python3 router.py router_name
- python3 host.py host_name

RUN THE TESTS WITH:
- python3 -m unittest test_packet -v

(run everything from the project folder, because topology.json is opened from the folder you are in)

## What this project is

This project is a small fake network that runs on one laptop. Every device (host or router) is its own python process with its own UDP port on 127.0.0.1. The file topology.json says which devices exist, what their virtual address (vaddr) and port is, and who their neighbors are. When a device starts, network.py loads this file, checks that it makes sense (no missing neighbors, no shared ports, links go both ways) and opens the socket.

Our network has two hosts (H1 and H2) and four routers (RA, RB, RC, RD). H1 is connected to RA and H2 is connected to RD, and in the middle there are two ways to go: through RB or through RC.

## The packet format

To send something between devices we needed our own packet format. We decided to use a small binary header followed by the payload, like real protocols (IP, UDP) do. We could have used JSON, but then fields don't have a fixed size, and a binary header is easier to describe exactly.

Every packet is a 10 byte header + the payload:

| Field | Size | What it is |
|---|---|---|
| src | 2 bytes | vaddr of who sent it |
| dst | 2 bytes | vaddr of who it's for |
| hop_limit | 1 byte | how many more routers the packet can go through |
| msg_type | 1 byte | 1 = DATA, 2 = ECHO_REQUEST, 3 = ECHO_REPLY |
| msg_id | 4 bytes | id of the message, a reply uses the same id |
| payload | the rest | the actual data (bytes) |

The header is packed with python's struct module using the format "!HHBBI", where ! means network byte order, H is 2 bytes, B is 1 byte and I is 4 bytes. A full packet can be at most 2048 bytes, so the payload can be at most 2038 bytes.

We only put the fields the assignment asked for, to keep it simple. We didn't add a length field because UDP already keeps every message separate (one sendto arrives as one recvfrom), so the payload is just everything after the header. The addresses are 2 bytes even though ours only go from 1 to 14, so there is room for more devices later. The msg_id is 4 bytes so we don't run out of ids.

The hop limit starts at 16. The longest path in our network is 4 hops, so 16 is more than enough, and if a packet ever gets stuck in a loop it will still die at some point. Right now routers don't forward packets yet, so the hop limit isn't decreased anywhere yet. That will come with forwarding.

The payload is kept as raw bytes. The network only moves bytes and doesn't care what is inside. Text is turned into bytes (UTF-8) when sending and back into text only when printing, so weird bytes can't break anything.

## How a packet is read

All of this is in packet.py. encode() turns a Packet into bytes and decode() turns bytes back into a Packet. decode() checks the packet in this order:

1. if it is bigger than 2048 bytes it is rejected
2. if it is smaller than 10 bytes it is rejected, because there isn't even a full header
3. the 5 header fields are read from the first 10 bytes
4. if msg_type is not 1, 2 or 3 it is rejected
5. if hop_limit is 0 it is rejected, because it should have been dropped already
6. everything after the header becomes the payload

If any check fails, decode() gives a PacketError with the reason. encode() also refuses to build a bad packet (payload too big, unknown type, or a number that doesn't fit in its field), so we never send a broken packet ourselves. PacketError is the only error they give, so the code that uses them only has to catch one thing.

## What hosts and routers do with packets

host.py and router.py wait for packets forever. Every packet they get goes through decode(). A good packet is printed as a RECV line, a bad packet is printed as a DROP line with the reason, and the device just keeps going. So a bad packet never crashes a device. For example:

```
H1 RECV id=7 type=1 src=2 dst=1 hop=16 payload='hello H1'
H1 DROP from ('127.0.0.1', 54974): packet too short: 7 bytes
H1 DROP from ('127.0.0.1', 54974): packet too big: 2049 bytes
```

One tricky part was catching packets that are too big. If we ask the socket for 2048 bytes and someone sends 3000, the operating system silently cuts it to 2048 and we would never know. So we ask for 2049 bytes. If we really get 2049, we know the packet was too big and we drop it.

## About the message id

The message id is just a label. It helps match a request with its reply and find the same message in the logs of different devices. It does NOT make delivery reliable: if a packet gets lost nothing sends it again.

## Testing it

The unit tests in test_packet.py check that packets come back the same after encode() and decode(), and that every kind of bad packet is rejected.

To test it by hand, start a host in one terminal:

```
python3 host.py H1
```

Then send it one good packet and one bad one from a second terminal:

```
python3 -c "
import socket
from packet import *
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.sendto(encode(Packet(2, 1, 16, DATA, 7, b'hello H1')), ('127.0.0.1', 5001))
s.sendto(b'garbage', ('127.0.0.1', 5001))
"
```

H1 should print one RECV line and one DROP line and keep running. Stop it with Ctrl+C.

## Files
- topology.json: all the devices, their vaddr, port and neighbors
- network.py: loads and checks topology.json, then opens the UDP socket for a device
- packet.py: the packet format, encode() and decode()
- host.py / router.py: start a device, decode every packet and print RECV or DROP
- test_packet.py: tests for packet.py
