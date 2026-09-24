"""The circuit, drawn (US6).

`qc.draw("mpl")` deliberately, not a hand-rolled SVG. This is the diagram from
every Qiskit tutorial and paper, and the point is RECOGNISABILITY rather than
aesthetics: a reader who knows the field parses it without thinking, where a
prettier custom rendering would read as unfamiliar and invite attention to the
drawing instead of the circuit.

Rendered from the QPY `static_check` already produced, so generated code is
never executed a second time outside the sandbox — the same rule the semantic
checks and the distribution follow.
"""

import base64
import io

from qiskit import QuantumCircuit

# Past this, the drawing is a wall of wires nobody reads and the PNG gets
# large enough to bloat an SSE frame. Reported as a reason, never silently
# skipped: an absent diagram with no explanation looks like a failure.
MAX_DRAWABLE_QUBITS = 12
MAX_DRAWABLE_OPS = 120


def circuit_png(circuit: QuantumCircuit) -> tuple[str | None, str | None]:
    """`(data_uri, reason_it_is_missing)` — exactly one is non-None.

    Returns a data URI rather than a served file: the interface keeps nothing
    on disk (it is read-only with respect to results/), and a base64 PNG of a
    small circuit is a few KB.
    """
    if circuit.num_qubits > MAX_DRAWABLE_QUBITS:
        return None, f"{circuit.num_qubits} qubits — too wide to read as a diagram"
    if len(circuit.data) > MAX_DRAWABLE_OPS:
        return None, f"{len(circuit.data)} operations — too dense to read as a diagram"

    try:
        import matplotlib

        # Must precede pyplot: the container has no display, and the
        # interactive backend would try to find one and fail.
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        figure = circuit.draw("mpl", idle_wires=False, fold=24)
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", dpi=150, bbox_inches="tight", transparent=True)
        plt.close(figure)
    except Exception as exc:  # noqa: BLE001 — a missing diagram is cosmetic
        # Never fatal. The diagram is the nicest thing on the page and the
        # least important: a run that verified is still verified without it.
        return None, f"could not be drawn ({type(exc).__name__})"

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}", None
