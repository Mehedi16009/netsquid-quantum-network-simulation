import netsquid as ns
import numpy as np
import matplotlib.pyplot as plt

from netsquid.nodes import Node
from netsquid.components import QuantumChannel
from netsquid.components.models import FibreLossModel   # <--- FIXED
from netsquid.protocols import NodeProtocol
from netsquid.qubits import ketstates, qubitapi


# -----------------------------
# Parameters
# -----------------------------
distances_km = np.linspace(0, 100, 11)   # 0–100 km
shots = 200                              # M1-safe
fiber_loss_db_per_km = 0.2               # standard telecom fiber

success_probs = []


# -----------------------------
# Bell source protocol
# -----------------------------
class BellSource(NodeProtocol):
    def run(self):
        q1, q2 = ns.qubits.create_qubits(2)
        ns.qubits.assign_qstate([q1, q2], ketstates.b00)
        self.node.ports["qout_A"].tx_output(q1)
        self.node.ports["qout_B"].tx_output(q2)


# -----------------------------
# Sweep over distances
# -----------------------------
for distance in distances_km:
    successes = 0

    for _ in range(shots):
        ns.sim_reset()

        # Nodes
        source = Node("Source")
        alice = Node("Alice")
        bob = Node("Bob")

        source.add_ports(["qout_A", "qout_B"])
        alice.add_ports(["qin"])
        bob.add_ports(["qin"])

        # Fiber loss model (length NOT included here)
        loss_model = FibreLossModel(
          p_loss_init=0.0,
        p_loss_length=fiber_loss_db_per_km )

        chan_A = QuantumChannel(
          "chan_A",
        length=distance * 1000,
        models={"loss_model": loss_model}
                                     )

        chan_B = QuantumChannel(
        "chan_B",
        length=distance * 1000,
        models={"loss_model": loss_model}
                              )


        source.ports["qout_A"].connect(chan_A.ports["send"])
        chan_A.ports["recv"].connect(alice.ports["qin"])

        source.ports["qout_B"].connect(chan_B.ports["send"])
        chan_B.ports["recv"].connect(bob.ports["qin"])

        received = {"alice": None, "bob": None}

        def alice_handler(msg):
            received["alice"] = msg.items[0]

        def bob_handler(msg):
            received["bob"] = msg.items[0]

        alice.ports["qin"].bind_input_handler(alice_handler)
        bob.ports["qin"].bind_input_handler(bob_handler)

        BellSource(source).start()
        ns.sim_run()

        # Success = both qubits arrived
        if received["alice"] is not None and received["bob"] is not None:
            successes += 1

    success_probs.append(successes / shots)
    print(f"Distance {distance:.1f} km: success = {successes/shots:.3f}")


# -----------------------------
# Plot results
# -----------------------------
plt.figure(figsize=(5, 4))
plt.plot(distances_km, success_probs, "o-", linewidth=2)
plt.xlabel("Distance (km)")
plt.ylabel("Success Probability")
plt.title("Bell Pair Success vs Distance")
plt.grid(True)
plt.tight_layout()
plt.savefig("outputs/success_vs_distance.pdf")
plt.close()
