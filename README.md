START THIS PROJECT WITH EITHER: 
- python3 router.py router_name
- python3 host.py host_name

RUN THE TESTS WITH:
- python3 -m unittest test_packet -v

## Files
- topology.json: all the devices, their virtual address (vaddr), port and neighbors
- network.py: loads and checks topology.json, then opens the UDP socket for a device
- host.py / router.py: start a host or a router
- packet.py: the packet format, encode() and decode()
- test_packet.py: tests for packet.py

## Packet format
Every packet is a 10 byte header + the payload.

| Field | Size | What it is |
|---|---|---|
| src | 2 bytes | vaddr of who sent it |
| dst | 2 bytes | vaddr of who it's for |
| hop_limit | 1 byte | goes down by 1 at each router, the packet is dropped at 0 |
| msg_type | 1 byte | 1 = DATA, 2 = ECHO_REQUEST, 3 = ECHO_REPLY |
| msg_id | 4 bytes | id of the message, a reply uses the same id |
| payload | the rest | the actual data (bytes) |

- The header is packed with python's struct module ("!HHBBI") in network byte order
- Max packet size is 2048 bytes, so the payload can be at most 2038 bytes
- Default hop limit is 16

## How a packet is parsed (decode)
The checks happen in this order, and if one fails we get a PacketError:
1. bigger than 2048 bytes -> rejected
2. smaller than 10 bytes -> rejected (not even a full header)
3. read the 5 header fields from the first 10 bytes
4. msg_type is not 1, 2 or 3 -> rejected
5. hop_limit is 0 -> rejected
6. everything after the header is the payload

encode() does the opposite and also refuses to build a bad packet (payload too big, unknown type, or a number that doesn't fit in its field).

## Why we did it this way
- **Binary header instead of JSON:** every field has a fixed size, like real headers (IP, UDP), and it is easy to document
- **Only the required fields:** we kept the header as small and simple as possible
- **No length field:** UDP keeps each message separate (one sendto = one recvfrom), so the payload is just everything after the header
- **vaddr is 2 bytes:** our addresses are small now (1 to 14), but this leaves room for more devices
- **msg_id is 4 bytes:** lots of ids before they run out
- **Hop limit 16:** the longest path in our topology is 4 hops, so 16 is more than enough, and if there is ever a loop the packet still dies
- **Payload is raw bytes:** the network just moves bytes and doesn't care what they are. Text is turned into bytes (UTF-8) only when sending and back to text when printing
- **Only one error type (PacketError):** so the receive loop only has to catch one thing and a bad packet never crashes the device

## About the message id
The message id is just a label. It helps match a request with its reply and find the same message in the logs of different devices. It does NOT make delivery reliable: if a packet gets lost nothing sends it again.
