import json, random, socket, sys, threading

from logger import log_event, set_run
from packet import encode

#one random generator per link, made from the seed in topology.json so a run can be repeated
link_randoms = {}

"""
LOADS CONFIGURATION FILE 
"""
def load_config(path="topology.json"):
    try:
        with open(path) as config: 
            return json.load(config)

    except (FileNotFoundError, json.JSONDecodeError) as err:
        sys.exit(f"Error loading config: {err}")

"""
VALIDATES CONFIG INPUTS
- This function takes in the config, a device name, and the type of that device (EX: H1, host)
- Checks if the device is in the config
- Checks if the entered device type is correct for the device 
- Checks if there is a duplicate port in any of the devices 
- Checks if the neigbors of the device exists in the config so there arent any "ghost nodes"
- Checks if the connection between the device and its neighbor is bidirectional/mutual 
"""
def validate_config(config, device_name, device_type):
    if device_name not in config: 
        sys.exit(f"ERR: There was no router or host named {device_name}")

    if config[device_name]["type"] != device_type:
        sys.exit(f"ERR: {device_name} is a {config[device_name]['type']} not {device_type}")

    unique_ports = set()

    for device in config.values():
        unique_ports.add(device["port"])

    if len(unique_ports) != len(config):
        sys.exit("ERR: Two devices share the same port") 

    for device, device_info in config.items():
        for neighbor in device_info["neighbors"]:

            if neighbor not in config:
                sys.exit(f"ERR: {device} has a neighbor that doesn't exist: {neighbor} ")

            if device not in config[neighbor]["neighbors"]:
                sys.exit("ERR: Connection between devices is one sided")

"""
START A DEVICE
- This function takes in device_name, device_type and the run name (EX: H1, host, demo1)
- Loads config
- Validates config
- Sets the run name for the logs and logs the link conditions of this device (where + seed)
- Sets PORT to the port assigned to the device in the config
- Sets HOST to the default 127.0.0.1
- Creates the server_socket (socket.AF_INET = IPv4, socket.SOCK.DGRAM = UDP)
- Binds the socket to the HOST and PORT
- returns the device_name, config, and the server_socket object
"""
def start(device_name, device_type, run="run"):

    config = load_config()
    validate_config(config, device_name, device_type)

    set_run(run)
    for next_hop, condition in config[device_name].get("link_conditions", {}).items():
        log_event(
            device_name, "CONDITION", next_hop=next_hop,
            note=f"link={device_name}->{next_hop} loss={condition['loss']} "
                 f"delay={condition['delay']} seed={condition['seed']}"
        )

    PORT = config[device_name]["port"]
    HOST = "127.0.0.1"

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((HOST, PORT))

    print(f"{device_type} {device_name} listening on {HOST}:{PORT}")

    return device_name, config, server_socket


"""
SEND OVER LINK
- Sends a packet from device_name to its neighbor next_hop
- If topology.json has link_conditions for this link (device_name -> next_hop):
  - loss: the packet is dropped with that chance (0.0 to 1.0) and a DROP is logged
  - delay: the packet is sent after that many seconds, on a timer so the device doesn't wait
- Every packet type goes through here, so the conditions hit all of them
"""
def send_over_link(device_name, config, server_socket, packet, next_hop):
    data = encode(packet)
    address = ("127.0.0.1", config[next_hop]["port"])
    condition = config[device_name].get("link_conditions", {}).get(next_hop)

    #no conditions on this link, send right away like before
    if condition is None:
        server_socket.sendto(data, address)
        return

    link = (device_name, next_hop)
    if link not in link_randoms:
        link_randoms[link] = random.Random(condition["seed"])

    if link_randoms[link].random() < condition["loss"]:
        log_event(device_name, "DROP", packet, next_hop, note=f"link loss {device_name}->{next_hop}")
        return

    if condition["delay"] > 0:
        #the timer sends it later on its own thread, the main loop keeps handling other packets
        threading.Timer(condition["delay"], server_socket.sendto, args=(data, address)).start()
    else:
        server_socket.sendto(data, address)







    



