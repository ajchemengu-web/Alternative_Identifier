"""Post-run metrics from a simulation log."""
from __future__ import annotations

import numpy as np

# Servo electrical model used for the energy proxy (assumption, tune to the
# real actuator): copper loss P = (tau / Km)^2 with motor constant Km in
# N*m/sqrt(W) (a ~3 N*m hobby servo stalls at ~12 W -> ~0.85), plus positive mechanical work (no regeneration).
MOTOR_CONST = 0.8


def energy(L: dict, i0: int, i1: int, km: float = MOTOR_CONST) -> dict:
    t = L["t"][i0:i1]
    if len(t) < 2:
        return dict(mech_J=0.0, elec_J=0.0, dt=0.0)
    dt = np.gradient(t)
    tau, qd = L["tau"][i0:i1], L["qd"][i0:i1]
    wtau, wqd = L["wtau"][i0:i1], L["wqd"][i0:i1]
    mech = np.maximum(tau * qd, 0).sum(1) + np.maximum(wtau * wqd, 0).sum(1)
    cu = ((tau / km) ** 2).sum(1) + ((wtau / km) ** 2).sum(1)
    return dict(mech_J=float((mech * dt).sum()),
                elec_J=float(((mech + cu) * dt).sum()),
                dt=float(t[-1] - t[0]))


def cost_of_transport(e_joules: float, mass: float, dist: float, g=9.81) -> float:
    return e_joules / (mass * g * max(dist, 1e-6))
