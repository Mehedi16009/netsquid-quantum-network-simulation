import netsquid as ns
import numpy as np
import matplotlib.pyplot as plt

from netsquid.nodes import Node
from netsquid.components import QuantumChannel
from netsquid.components.models import FibreLossModel
from netsquid.protocols import NodeProtocol
from netsquid.qubits import ketstates, qubitapi
from netsquid.qubits.operators import H, CNOT  # Correct operator import

# -----------------------------
# Simulation parameters
# -----------------------------
shots = 100       # M1-friendly
fiber_loss_db_per_km = 0.2
distance_km = 50  # Each link
success_fidelities = []

# -----------------------------
# Protocols
# -----------------------------
class BellSource(NodeProtocol):
    def run(self):
        q1, q2 = ns.qubits.create_qubits(2)
        ns.qubits.assign_qstate([q1, q2], ketstates.b00)
        self.node.ports["qout_1"].tx_output(q1)
        self.node.ports["qout_2"].tx_output(q2)

# -----------------------------
# Sweep over shots
# -----------------------------
for _ in range(shots):
    ns.sim_reset()

    # Nodes
    alice = Node("Alice")
    middle = Node("Middle")
    bob = Node("Bob")
    source1 = Node("Source1")
    source2 = Node("Source2")

    # Add ports
    alice.add_ports(["qin"])
    middle.add_ports(["qin1", "qin2"])
    bob.add_ports(["qin"])
    source1.add_ports(["qout_1", "qout_2"])
    source2.add_ports(["qout_1", "qout_2"])

    # Fiber loss model
    loss_model = FibreLossModel(p_loss_init=0.0, p_loss_length=fiber_loss_db_per_km)

    # Channels: one channel per qubit
    chan_Alice_Middle_1 = QuantumChannel("chan_Alice_Middle_1", length=distance_km*1000,
                                         models={"loss_model": loss_model})
    chan_Alice_Middle_2 = QuantumChannel("chan_Alice_Middle_2", length=distance_km*1000,
                                         models={"loss_model": loss_model})

    source1.ports["qout_1"].connect(chan_Alice_Middle_1.ports["send"])
    chan_Alice_Middle_1.ports["recv"].connect(alice.ports["qin"])

    source1.ports["qout_2"].connect(chan_Alice_Middle_2.ports["send"])
    chan_Alice_Middle_2.ports["recv"].connect(middle.ports["qin1"])

    chan_Middle_Bob_1 = QuantumChannel("chan_Middle_Bob_1", length=distance_km*1000,
                                       models={"loss_model": loss_model})
    chan_Middle_Bob_2 = QuantumChannel("chan_Middle_Bob_2", length=distance_km*1000,
                                       models={"loss_model": loss_model})

    source2.ports["qout_1"].connect(chan_Middle_Bob_1.ports["send"])
    chan_Middle_Bob_1.ports["recv"].connect(middle.ports["qin2"])

    source2.ports["qout_2"].connect(chan_Middle_Bob_2.ports["send"])
    chan_Middle_Bob_2.ports["recv"].connect(bob.ports["qin"])

    # Storage
    received = {"alice": None, "middle1": None, "middle2": None, "bob": None}

    # Handlers
    def alice_handler(msg): received["alice"] = msg.items[0]
    def middle1_handler(msg): received["middle1"] = msg.items[0]
    def middle2_handler(msg): received["middle2"] = msg.items[0]
    def bob_handler(msg): received["bob"] = msg.items[0]

    alice.ports["qin"].bind_input_handler(alice_handler)
    middle.ports["qin1"].bind_input_handler(middle1_handler)
    middle.ports["qin2"].bind_input_handler(middle2_handler)
    bob.ports["qin"].bind_input_handler(bob_handler)

    # Start protocols
    BellSource(source1).start()
    BellSource(source2).start()
    ns.sim_run()

    # -----------------------------
    # Entanglement swapping (Middle performs BSM)
    # -----------------------------
    if received["alice"] is not None and received["middle1"] is not None \
       and received["middle2"] is not None and received["bob"] is not None:

        # Apply Hadamard on middle1 qubit
        ns.qubits.operate(received["middle1"], H)

        # Apply CNOT: control = middle1, target = middle2
        ns.qubits.operate([received["middle1"], received["middle2"]], CNOT)

        # Compute fidelity of Alice-Bob pair
        fid = qubitapi.fidelity([received["alice"], received["bob"]], ketstates.b00)
        success_fidelities.append(fid)

# -----------------------------
# Plot results
# -----------------------------
plt.figure(figsize=(5,4))
plt.hist(success_fidelities, bins=10, range=(0,1), color='skyblue', edgecolor='black')
plt.xlabel("Fidelity after swapping")
plt.ylabel("Counts")
plt.title("Entanglement Swapping Fidelity")
plt.tight_layout()
plt.savefig("outputs/swapping_fidelity.pdf")
plt.close()

print(f"Average fidelity: {np.mean(success_fidelities):.4f}")
