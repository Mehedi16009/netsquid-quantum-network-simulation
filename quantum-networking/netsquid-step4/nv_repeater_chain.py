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
num_repeaters = 2
link_distance_km = 20
success_fidelities = []

for shot in range(shots):
    ns.sim_reset()
    
    # Create NEW nodes for each shot
    alice = Node("Alice")
    repeaters = [Node(f"R{i}") for i in range(num_repeaters)]
    bob = Node("Bob")
    
    # Add ports to nodes
    alice.add_ports(["qin", "qout_right"])
    bob.add_ports(["qin"])
    
    for r in repeaters:
        r.add_ports(["qin_left", "qin_right", "qout_right"])
    
    # Build the chain: Alice -> R0 -> R1 -> ... -> Bob
    nodes_chain = [alice] + repeaters + [bob]
    
    # Create loss model
    loss_model = FibreLossModel(p_loss_init=0.0, p_loss_length=fiber_loss_db_per_km)
    
    # Create quantum channels between adjacent nodes
    channels = []
    
    # Connect Alice to first repeater (or Bob if no repeaters)
    if num_repeaters > 0:
        # Alice to R0
        chan_alice_r0 = QuantumChannel(
            f"chan_alice_r0", 
            length=link_distance_km*1000, 
            models={"loss_model": loss_model}
        )
        alice.ports["qout_right"].connect(chan_alice_r0.ports["send"])
        chan_alice_r0.ports["recv"].connect(repeaters[0].ports["qin_left"])
        channels.append(chan_alice_r0)
        
        # Connect repeaters in chain
        for i in range(num_repeaters - 1):
            chan = QuantumChannel(
                f"chan_r{i}_r{i+1}", 
                length=link_distance_km*1000, 
                models={"loss_model": loss_model}
            )
            repeaters[i].ports["qout_right"].connect(chan.ports["send"])
            chan.ports["recv"].connect(repeaters[i+1].ports["qin_left"])
            channels.append(chan)
        
        # Connect last repeater to Bob
        chan_rn_bob = QuantumChannel(
            f"chan_r{num_repeaters-1}_bob", 
            length=link_distance_km*1000, 
            models={"loss_model": loss_model}
        )
        repeaters[-1].ports["qout_right"].connect(chan_rn_bob.ports["send"])
        chan_rn_bob.ports["recv"].connect(bob.ports["qin"])
        channels.append(chan_rn_bob)
    else:
        # Direct connection Alice to Bob
        chan_alice_bob = QuantumChannel(
            "chan_alice_bob", 
            length=link_distance_km*1000, 
            models={"loss_model": loss_model}
        )
        alice.ports["qout_right"].connect(chan_alice_bob.ports["send"])
        chan_alice_bob.ports["recv"].connect(bob.ports["qin"])
        channels.append(chan_alice_bob)
    
    # Track received qubits
    received = {}
    
    # Set up input handlers for all receiving ports
    def make_handler(node_name, port_name):
        def handler(msg):
            if msg.items:
                received[f"{node_name}_{port_name}"] = msg.items[0]
        return handler
    
    # Alice receives her half of Bell pair
    alice.ports["qin"].bind_input_handler(make_handler("Alice", "qin"))
    
    # Repeaters receive qubits on both sides
    for i, r in enumerate(repeaters):
        r.ports["qin_left"].bind_input_handler(make_handler(f"R{i}", "qin_left"))
        if i < num_repeaters - 1:
            r.ports["qin_right"].bind_input_handler(make_handler(f"R{i}", "qin_right"))
    
    # Bob receives his qubit
    bob.ports["qin"].bind_input_handler(make_handler("Bob", "qin"))
    
    # Generate initial Bell pairs
    # Alice keeps one qubit and sends others down the chain
    q_alice, q_to_chain = ns.qubits.create_qubits(2)
    ns.qubits.assign_qstate([q_alice, q_to_chain], ketstates.b00)
    received["Alice_qin"] = q_alice
    alice.ports["qout_right"].tx_output(q_to_chain)
    
    # Each repeater generates a Bell pair and sends one half to the next node
    for i in range(num_repeaters - 1):
        q_local, q_forward = ns.qubits.create_qubits(2)
        ns.qubits.assign_qstate([q_local, q_forward], ketstates.b00)
        repeaters[i].ports["qout_right"].tx_output(q_forward)
        received[f"R{i}_qin_right"] = q_local
    
    # Last repeater sends to Bob
    if num_repeaters > 0:
        q_last_rep, q_to_bob = ns.qubits.create_qubits(2)
        ns.qubits.assign_qstate([q_last_rep, q_to_bob], ketstates.b00)
        repeaters[-1].ports["qout_right"].tx_output(q_to_bob)
        received[f"R{num_repeaters-1}_qin_right"] = q_last_rep
    
    # Run simulation to propagate qubits through channels
    ns.sim_run()
    
    # Perform Bell state measurements at repeaters (entanglement swapping)
    for i in range(num_repeaters):
        q_left = received.get(f"R{i}_qin_left")
        q_right = received.get(f"R{i}_qin_right")
        
        if q_left is not None and q_right is not None:
            # Bell state measurement - correct syntax
            ns.qubits.operate([q_left, q_right], CNOT)
            ns.qubits.operate(q_right, H)
    
    # Check final fidelity between Alice and Bob's qubits
    q_alice = received.get("Alice_qin")
    q_bob = received.get("Bob_qin")
    
    if q_alice is not None and q_bob is not None:
        fid = qubitapi.fidelity([q_alice, q_bob], ketstates.b00)
        success_fidelities.append(fid)
        if (shot + 1) % 10 == 0:
            print(f"Shot {shot+1}/{shots}: Fidelity = {fid:.4f}")
    else:
        if (shot + 1) % 10 == 0:
            print(f"Shot {shot+1}/{shots}: Qubits lost")

# Create outputs directory if it doesn't exist
os.makedirs("outputs", exist_ok=True)

# Plot results
if success_fidelities:
    plt.figure(figsize=(5, 4))
    plt.hist(success_fidelities, bins=10, range=(0, 1), color='lightgreen', edgecolor='black')
    plt.xlabel("Fidelity")
    plt.ylabel("Counts")
    plt.title(f"NV Repeater Chain Fidelity ({num_repeaters} repeaters)")
    plt.tight_layout()
    plt.savefig("outputs/nv_repeater_chain_fidelity.pdf")
    plt.close()
    
    print(f"\nResults:")
    print(f"Average fidelity: {np.mean(success_fidelities):.4f}")
    print(f"Success rate: {len(success_fidelities)}/{shots} ({100*len(success_fidelities)/shots:.1f}%)")
    print(f"Plot saved to outputs/nv_repeater_chain_fidelity.pdf")
else:
    print("No successful entanglement distributions!")
