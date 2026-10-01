import json, socket, sys 

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
- This function takes in device_name and device_type (EX: H1, host)
- Loads config
- Validates config 
- Sets PORT to the port assigned to the device in the config 
- Sets HOST to the default 127.0.0.1
- Creates the server_socket (socket.AF_INET = IPv4, socket.SOCK.DGRAM = UDP)
- Binds the socket to the HOST and PORT
- returns the device_name, config, and the server_socket object
"""
def start(device_name, device_type):

    config = load_config()
    validate_config(config, device_name, device_type)

    PORT = config[device_name]["port"]
    HOST = "127.0.0.1"

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((HOST, PORT))

    print(f"{device_type} {device_name} listening on {HOST}:{PORT}")

    return device_name, config, server_socket







    



