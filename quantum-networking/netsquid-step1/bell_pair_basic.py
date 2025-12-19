import netsquid as ns
import numpy as np
import matplotlib.pyplot as plt

from netsquid.nodes import Node
from netsquid.components import QuantumChannel
from netsquid.protocols import NodeProtocol
from netsquid.qubits import ketstates, qubitapi


# -----------------------------
# Protocol: Create Bell Pair
# -----------------------------
class BellSourceProtocol(NodeProtocol):
    def run(self):
        # Create Bell pair |Phi+>
        q1, q2 = ns.qubits.create_qubits(2)
        ns.qubits.assign_qstate([q1, q2], ketstates.b00)

        # Send qubits
        self.node.ports["qout_A"].tx_output(q1)
        self.node.ports["qout_B"].tx_output(q2)


# -----------------------------
# Setup nodes
# -----------------------------
alice = Node("Alice")
bob = Node("Bob")
source = Node("Source")

# Explicit ports
source.add_ports(["qout_A", "qout_B"])
alice.add_ports(["qin"])
bob.add_ports(["qin"])

# Quantum channels (ideal, no noise)
chan_A = QuantumChannel("chan_A")
chan_B = QuantumChannel("chan_B")

# Connect network
source.ports["qout_A"].connect(chan_A.ports["send"])
chan_A.ports["recv"].connect(alice.ports["qin"])

source.ports["qout_B"].connect(chan_B.ports["send"])
chan_B.ports["recv"].connect(bob.ports["qin"])

# Storage
received = {"alice": None, "bob": None}


# -----------------------------
# Handlers
# -----------------------------
def alice_handler(msg):
    received["alice"] = msg.items[0]


def bob_handler(msg):
    received["bob"] = msg.items[0]


alice.ports["qin"].bind_input_handler(alice_handler)
bob.ports["qin"].bind_input_handler(bob_handler)

# -----------------------------
# Run protocol
# -----------------------------
BellSourceProtocol(source).start()
ns.sim_run()

# -----------------------------
# Fidelity computation
# -----------------------------
qA = received["alice"]
qB = received["bob"]

fid = qubitapi.fidelity([qA, qB], ketstates.b00)


print(f"Bell-state fidelity: {fid:.4f}")

# -----------------------------
# Save figure
# -----------------------------
plt.figure(figsize=(4, 3))
plt.bar(["Bell Pair"], [fid])
plt.ylim(0, 1.05)
plt.ylabel("Fidelity")
plt.title("Bell Pair Fidelity")
plt.tight_layout()
plt.savefig("outputs/bell_fidelity.pdf")
plt.close()
