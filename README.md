START THIS PROJECT WITH EITHER: 
- python3 router.py router_name
- python3 host.py host_name

To send an echo request between hosts, start the destination host and routers
first, then run a source host with:

```
python3 host.py H1 --send-to 2 --message "hello H2"
```

The source prints `OK` when a matching echo reply (same message id) arrives,
or an explicit `TIMEOUT` if none arrives within 2 seconds (`RESPONSE_TIMEOUT`
in host.py). Each probe is sent once and never retransmitted. Hosts run in
listener mode when `--send-to` is omitted.

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
run=run time=2026-10-20T12:00:01.120 device=H1 event=RECV id=7 type=DATA src=2 dst=1 hop=16 note=payload='hello H1'
run=run time=2026-10-20T12:00:02.310 device=H1 event=DROP note=packet too short: 7 bytes from ('127.0.0.1', 54974)
run=run time=2026-10-20T12:00:03.450 device=H1 event=DROP note=packet too big: 2049 bytes from ('127.0.0.1', 54974)
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

To send in the other direction, stop H1 and H2, start H1 as a listener with
`python3 host.py H1`, then run `python3 host.py H2 --send-to 1 --message "hello H1"`.

The default route uses RB. Change the two documented route entries and restart
the routers to test the path through RC. Stop listener processes with Ctrl+C.

## Network conditions and logs

### Packet loss and delay on a link

A link can be made to lose packets and/or add delay. This is set in topology.json, inside the device that **sends** on the link, under `link_conditions`. The key is the neighbor at the other end, so this on RA means the directed link RA -> RB:

```
"RA": { ..., "link_conditions": {"RB": {"loss": 0.5, "delay": 0.2, "seed": 1}} }
```

- `loss`: chance from 0.0 to 1.0 that a packet on this link is dropped
- `delay`: extra seconds before the packet is delivered
- `seed`: seed for this link's random generator, so the same seed gives the same drops

To affect both directions (a bidirectional link pair), add the mirror entry on the other device too (`"RA": {...}` inside RB). topology.json already has the RA <-> RB pair set to 0 loss and 0 delay, so by default nothing changes. Change the numbers and restart the devices to use them.

All sending (by hosts and by routers) goes through one function, `send_over_link()` in network.py, so the conditions hit every packet type the same way: requests, replies and data. A lost packet is logged as a DROP with `note=link loss RA->RB`. A delayed packet is handed to a timer (`threading.Timer`) that sends it later, so the device does not wait and keeps handling other packets in the meantime.

At startup every device logs one CONDITION line per link it has conditions on, so the logs of a run always say where the conditions were and which seed was used:

```
run=demo1 time=2026-10-20T12:02:25.887 device=RA event=CONDITION next_hop=RB note=link=RA->RB loss=0.5 delay=0.2 seed=1
run=demo1 time=2026-10-20T12:02:25.887 device=RB event=CONDITION next_hop=RA note=link=RB->RA loss=0.0 delay=0.0 seed=2
```

A link failure can be simulated with `"loss": 1.0`: no packet gets through, and the host that sent the probe reports a TIMEOUT.

### Logs

Every device logs one line per event, with this information:

- `run`: the run name, given with `--run` (default `run`)
- `time`: date and time with milliseconds
- `device`: who wrote the line
- `event`: SEND, RECV, FWD, DROP, TIMEOUT, OK or CONDITION
- `id`, `type`, `src`, `dst`, `hop`: the packet's message id, message type, virtual source, virtual destination and hop limit
- `next_hop`: where the packet was sent (on SEND, FWD and link DROP lines)
- `note`: the reason for a DROP, the payload on a RECV, etc.

The lines are printed and also saved to `logs/<run>/<device>.log`. Give every device the same run name:

```
python3 router.py RA --run demo1     (same for RB, RC, RD)
python3 host.py H2 --run demo1
python3 host.py H1 --send-to 2 --message "hello H2" --run demo1
```

To follow one request and its reply through every device, search all the log files of the run for its message id:

```
grep -h "id=<message id> " logs/demo1/*.log | sort -s -k2,2
```

## Files
- topology.json: all the devices, their vaddr, port, neighbors, routes and link conditions
- network.py: loads and checks topology.json, opens the UDP socket for a device, and sends packets over a link (loss and delay)
- logger.py: writes the log lines (stdout and logs/<run>/<device>.log)
- packet.py: the packet format, encode() and decode()
- host.py / router.py: run hosts and routers, including echo requests and static forwarding
- test_packet.py / test_forwarding.py / test_network.py: packet, forwarding and link condition tests
