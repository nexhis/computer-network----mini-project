START THIS PROJECT WITH EITHER: 
- python3 router.py router_name
- python3 host.py host_name

To send an echo request between hosts, start the destination host and routers
first, then run a source host with:

```
python3 host.py H1 --send-to 2 --message "hello H2" --timeout 3
```

The source prints an explicit `TIMEOUT` if no matching echo reply arrives
before the timeout. Hosts run in listener mode when `--send-to` is omitted.

RUN THE TESTS WITH:
- python3 -m unittest -v

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

The hop limit starts at 16. Each router discards a packet with an incoming
hop limit of 1 or less. Otherwise it decrements the limit by one before
forwarding. A host is not a router and does not decrement the limit. A zero
hop limit is decoded as a packet so a router can log it specifically as an
exhausted-hop-limit drop.

The payload is kept as raw bytes. The network only moves bytes and doesn't care what is inside. Text is turned into bytes (UTF-8) when sending and back into text only when printing, so weird bytes can't break anything.

## How a packet is read

All of this is in packet.py. encode() turns a Packet into bytes and decode() turns bytes back into a Packet. decode() checks the packet in this order:

1. if it is bigger than 2048 bytes it is rejected
2. if it is smaller than 10 bytes it is rejected, because there isn't even a full header
3. the 5 header fields are read from the first 10 bytes
4. if msg_type is not 1, 2 or 3 it is rejected
5. everything after the header becomes the payload. Routers apply the
   hop-limit forwarding rule so the drop is logged with its specific reason.

If any check fails, decode() gives a PacketError with the reason. encode() also refuses to build a bad packet (payload too big, unknown type, or a number that doesn't fit in its field), so we never send a broken packet ourselves. PacketError is the only error they give, so the code that uses them only has to catch one thing.

## Static forwarding and hosts

Each router has a `routes` table in `topology.json`. Keys are destination
virtual addresses, written as JSON strings, and values are the names of
neighboring devices to use as next hop. The tables are manually configured;
there is no shortest-path algorithm or automatic recovery. The initial
configuration routes from H1 to H2 through RB and routes replies back through
RB. To use the lower path through RC instead, change these two entries:

```
RA routes["2"]: "RB" -> "RC"
RD routes["1"]: "RB" -> "RC"
```

Restart the devices after changing the tables. Routes at RB and RC are already
configured to support forwarding in either direction. If the selected link is
down, packets are lost and the sending host reports a timeout rather than
waiting forever.

Routers forward payloads unchanged as bytes. They log drops for an exhausted
hop limit, an unknown destination, or an invalid next hop. Hosts accept packets
addressed to their own virtual address. An echo-requesting host sends an
`ECHO_REQUEST`; the addressed host sends back an `ECHO_REPLY` with the same
message ID and payload.

Every received packet is decoded. A malformed packet is printed as a DROP line
with the reason, and the device keeps running. For example:

```
H1 RECV id=7 type=1 src=2 dst=1 hop=16 payload='hello H1'
H1 DROP from ('127.0.0.1', 54974): packet too short: 7 bytes
H1 DROP from ('127.0.0.1', 54974): packet too big: 2049 bytes
```

One tricky part was catching packets that are too big. If we ask the socket for 2048 bytes and someone sends 3000, the operating system silently cuts it to 2048 and we would never know. So we ask for 2049 bytes. If we really get 2049, we know the packet was too big and we drop it.

## About the message id

The message id is just a label. It helps match a request with its reply and find the same message in the logs of different devices. It does NOT make delivery reliable: if a packet gets lost nothing sends it again.

## Testing it

The unit tests check packet encoding/decoding and router forwarding behavior.

To test an end-to-end request, start all four routers, then start H2 as a host
listener:

```
python3 host.py H2
```

In another terminal, start H1 and send an echo request:

```
python3 host.py H1 --send-to 2 --message "hello H2"
```

The default route uses RB. Change the two documented route entries and restart
the routers to test the path through RC. Stop listener processes with Ctrl+C.

## Files
- topology.json: all the devices, their vaddr, port and neighbors
- network.py: loads and checks topology.json, then opens the UDP socket for a device
- packet.py: the packet format, encode() and decode()
- host.py / router.py: run hosts and routers, including echo requests and static forwarding
- test_packet.py / test_forwarding.py: packet and forwarding tests
