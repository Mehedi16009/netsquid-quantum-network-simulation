import netsquid as ns
import numpy as np
import matplotlib.pyplot as plt
from netsquid.nodes import Node
from netsquid.components import QuantumChannel
from netsquid.components.models import FibreLossModel
from netsquid.protocols import NodeProtocol
from netsquid.qubits import ketstates, qubitapi
from netsquid.qubits.operators import H, CNOT
import os

shots = 100
fiber_loss_db_per_km = 0.2
link_distance_km = 20
num_clients = 3  # number of nodes connected to switch
success_fidelities = []
entanglement_rates = []

class BellSource(NodeProtocol):
    def __init__(self, node, port1, port2):
        super().__init__(node)
        self.port1 = port1
        self.port2 = port2
    
    def run(self):
        q1, q2 = ns.qubits.create_qubits(2)
        ns.qubits.assign_qstate([q1, q2], ketstates.b00)
        self.node.ports[self.port1].tx_output(q1)
        self.node.ports[self.port2].tx_output(q2)

# -----------------------------
# Simulation
# -----------------------------
for shot in range(shots):
    ns.sim_reset()
    
    # Create NEW nodes for each shot to avoid port connection errors
    switch = Node("Switch")
    clients = [Node(f"C{i}") for i in range(num_clients)]
    
    # Add unique ports for each client connection on the switch
    switch_ports = []
    for i in range(num_clients):
        switch.add_ports([f"qin_from_c{i}", f"qout_to_c{i}"])
        switch_ports.append((f"qin_from_c{i}", f"qout_to_c{i}"))
    
    # Add ports to clients
    for c in clients:
        c.add_ports(["qin", "qout"])
    
    loss_model = FibreLossModel(p_loss_init=0.0, p_loss_length=fiber_loss_db_per_km)
    channels = []
    
    # Connect each client to the switch
    for i, c in enumerate(clients):
        # Channel from switch to client
        chan_switch_to_client = QuantumChannel(
            f"chan_s2c{i}", 
            length=link_distance_km*1000, 
            models={"loss_model": loss_model}
        )
        switch.ports[f"qout_to_c{i}"].connect(chan_switch_to_client.ports["send"])
        chan_switch_to_client.ports["recv"].connect(c.ports["qin"])
        
        # Channel from client to switch
        chan_client_to_switch = QuantumChannel(
            f"chan_c{i}2s", 
            length=link_distance_km*1000, 
            models={"loss_model": loss_model}
        )
        c.ports["qout"].connect(chan_client_to_switch.ports["send"])
        chan_client_to_switch.ports["recv"].connect(switch.ports[f"qin_from_c{i}"])
        
        channels.append((chan_switch_to_client, chan_client_to_switch))
    
    received = {}
    
    # Set up input handlers
    def make_handler(node_name, port_name):
        def handler(msg):
            if msg.items:
                received[f"{node_name}_{port_name}"] = msg.items[0]
        return handler
    
    # Handlers for switch
    for i in range(num_clients):
        switch.ports[f"qin_from_c{i}"].bind_input_handler(
            make_handler("Switch", f"qin_from_c{i}")
        )
    
    # Handlers for clients
    for i, c in enumerate(clients):
        c.ports["qin"].bind_input_handler(make_handler(f"C{i}", "qin"))
    
    # Generate Bell pairs between switch and each client
    for i in range(num_clients):
        q_switch, q_to_client = ns.qubits.create_qubits(2)
        ns.qubits.assign_qstate([q_switch, q_to_client], ketstates.b00)
        
        # Switch keeps one qubit
        received[f"Switch_qin_from_c{i}"] = q_switch
        
        # Send other qubit to client
        switch.ports[f"qout_to_c{i}"].tx_output(q_to_client)
    
    # Run simulation to propagate qubits
    ns.sim_run()
    
    # -----------------------------
    # Entanglement swapping at switch
    # Swap between client 0 and client 1
    # -----------------------------
    q_from_c0 = received.get("Switch_qin_from_c0")
    q_from_c1 = received.get("Switch_qin_from_c1")
    
    if q_from_c0 is not None and q_from_c1 is not None:
        # Bell state measurement at switch
        ns.qubits.operate([q_from_c0, q_from_c1], CNOT)
        ns.qubits.operate(q_from_c1, H)
    
    # Check fidelity between client 0 and client 1 (they should now be entangled)
    qC0 = received.get("C0_qin")
    qC1 = received.get("C1_qin")
    
    if qC0 is not None and qC1 is not None:
        fid = qubitapi.fidelity([qC0, qC1], ketstates.b00)
        success_fidelities.append(fid)
        entanglement_rates.append(1)  # Success
        if (shot + 1) % 10 == 0:
            print(f"Shot {shot+1}/{shots}: Fidelity = {fid:.4f}")
    else:
        entanglement_rates.append(0)  # Failure
        if (shot + 1) % 10 == 0:
            print(f"Shot {shot+1}/{shots}: Qubits lost")

# Create outputs directory if it doesn't exist
os.makedirs("outputs", exist_ok=True)

# -----------------------------
# Plot results
# -----------------------------
if success_fidelities:
    # Fidelity histogram
    plt.figure(figsize=(5, 4))
    plt.hist(success_fidelities, bins=10, range=(0, 1), color='skyblue', edgecolor='black')
    plt.xlabel("Fidelity")
    plt.ylabel("Counts")
    plt.title(f"Quantum Switch Fidelity ({num_clients} clients)")
    plt.tight_layout()
    plt.savefig("outputs/quantum_switch_fidelity.pdf")
    plt.close()
    
    # Entanglement rate over time
    plt.figure(figsize=(6, 4))
    window_size = 10
    running_avg = np.convolve(entanglement_rates, np.ones(window_size)/window_size, mode='valid')
    plt.plot(range(len(running_avg)), running_avg, color='green', linewidth=2)
    plt.xlabel("Shot")
    plt.ylabel("Success Rate (moving average)")
    plt.title(f"Entanglement Success Rate ({num_clients} clients)")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig("outputs/quantum_switch_success_rate.pdf")
    plt.close()
    
    print(f"\nResults:")
    print(f"Average fidelity: {np.mean(success_fidelities):.4f}")
    print(f"Success rate: {len(success_fidelities)}/{shots} ({100*len(success_fidelities)/shots:.1f}%)")
    print(f"Plots saved to outputs/")
else:
    print("No successful entanglement distributions!")
