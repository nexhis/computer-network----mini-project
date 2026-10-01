from network import start
import sys

"""
- This module is the entry point to starting a host type device. Start this server with the command python3 host.py device_name
- Calls start() function from network.py and takes the three values (tuple) device_name, config object, and the server_socket object from start()
- Runs forever until inturrupted ready to recive packets (packets of size 2048 bytes allowed for now)
- Gets messages as data (contents) and address (address of who sent data)
- Prints the info when recived 
"""

device_name, config, server_socket = start(sys.argv[1], "host")

while True:
    data, address = server_socket.recvfrom(2048)
    print(f"{device_name} received {data} from {address}")
