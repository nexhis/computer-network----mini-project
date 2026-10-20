import os
from datetime import datetime

from packet import DATA, ECHO_REPLY, ECHO_REQUEST

#names to print instead of the type numbers
TYPE_NAMES = {DATA: "DATA", ECHO_REQUEST: "ECHO_REQUEST", ECHO_REPLY: "ECHO_REPLY"}

#name of the current run, None = only print (ex: in the unit tests)
run_name = None


"""
SET RUN
- Saves the run name so every log line has it
- Makes the logs/<run> folder where each device writes its own file
"""
def set_run(run):
    global run_name
    run_name = run
    os.makedirs(os.path.join("logs", run), exist_ok=True)


"""
LOG EVENT
- Builds one log line (run, time, device, event, and the packet fields if there is a packet)
- event is SEND, RECV, FWD, DROP, TIMEOUT, OK or CONDITION
- Prints the line and also adds it to logs/<run>/<device>.log
"""
def log_event(device, event, packet=None, next_hop=None, note=""):
    #full date + time with milliseconds, so lines from different devices can be put in order
    time = datetime.now().isoformat(timespec="milliseconds")
    line = f"run={run_name} time={time} device={device} event={event}"

    if packet is not None:
        msg_type = TYPE_NAMES.get(packet.msg_type, packet.msg_type)
        line += (
            f" id={packet.msg_id} type={msg_type} src={packet.src}"
            f" dst={packet.dst} hop={packet.hop_limit}"
        )

    if next_hop is not None:
        line += f" next_hop={next_hop}"

    #note goes last because it can have spaces (ex: the drop reason)
    if note:
        line += f" note={note}"

    #flush so the line shows up right away even when output goes to a file
    print(line, flush=True)

    if run_name is not None:
        with open(os.path.join("logs", run_name, f"{device}.log"), "a") as log_file:
            log_file.write(line + "\n")
