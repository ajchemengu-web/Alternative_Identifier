"""Analytic leg kinematics for the 3-DOF wheel-legged hexapod.

Leg frame: hip at `hip`, leg direction yaw = mount_yaw + q1. In the vertical
plane of the leg, r is horizontal reach and z is up:
    r = coxa + femur*cos(q2) + tibia*cos(q2+q3)
    z =        femur*sin(q2) + tibia*sin(q2+q3)
q2 and q3 are positive "up"; the knee is always bent upward (elbow-up).
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .config import RobotConfig

LEGS = ("FL", "ML", "RL", "FR", "MR", "RR")
TRIPOD_A = ("FL", "MR", "RL")
TRIPOD_B = ("FR", "ML", "RR")
WHEEL_LEGS = ("FL", "FR", "RL", "RR")
MID_LEGS = ("ML", "MR")


@dataclass(frozen=True)
class LegGeometry:
    name: str
    hip: np.ndarray
    mount_yaw: float
    side: int          # +1 left, -1 right
    row: str           # "F", "M" or "R"
    has_wheel: bool


def leg_geometries(cfg: RobotConfig) -> dict[str, LegGeometry]:
    rows = {"F": cfg.hip_x, "M": 0.0, "R": -cfg.hip_x}
    out = {}
    for name in LEGS:
        row, side_c = name[0], name[1]
        side = 1 if side_c == "L" else -1
        out[name] = LegGeometry(
            name=name,
            hip=np.array([rows[row], side * cfg.hip_y, 0.0]),
            mount_yaw=side * math.pi / 2,
            side=side,
            row=row,
            has_wheel=row != "M",
        )
    return out


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def fk(cfg: RobotConfig, leg: LegGeometry, q) -> np.ndarray:
    """Tibia tip (= wheel centre or foot-sphere centre) in the body frame."""
    q1, q2, q3 = q
    r = cfg.coxa + cfg.femur * math.cos(q2) + cfg.tibia * math.cos(q2 + q3)
    z = cfg.femur * math.sin(q2) + cfg.tibia * math.sin(q2 + q3)
    yaw = leg.mount_yaw + q1
    return leg.hip + np.array([r * math.cos(yaw), r * math.sin(yaw), z])


def ik(cfg: RobotConfig, leg: LegGeometry, p_body):
    """Joint angles reaching `p_body`. Returns (q, violation).

    `violation` is 0 when the target is reachable inside all joint limits and
    otherwise the size (rad or m) of the worst infeasibility; the returned q
    is then the closest feasible configuration (clipped)."""
    v = np.asarray(p_body, float) - leg.hip
    viol = 0.0
    r = math.hypot(v[0], v[1])
    yaw = math.atan2(v[1], v[0]) if r > 1e-6 else leg.mount_yaw
    q1 = _wrap(yaw - leg.mount_yaw)

    a, b = r - cfg.coxa, v[2]
    d = math.hypot(a, b)
    d_min, d_max = abs(cfg.femur - cfg.tibia) + 1e-4, cfg.femur + cfg.tibia - 1e-4
    if d > d_max:
        viol = max(viol, d - d_max)
        d = d_max
    elif d < d_min:
        viol = max(viol, d_min - d)
        d = d_min
    phi = math.atan2(b, a)
    c_f = (cfg.femur**2 + d**2 - cfg.tibia**2) / (2 * cfg.femur * d)
    c_k = (cfg.femur**2 + cfg.tibia**2 - d**2) / (2 * cfg.femur * cfg.tibia)
    q2 = phi + math.acos(max(-1.0, min(1.0, c_f)))
    q3 = -(math.pi - math.acos(max(-1.0, min(1.0, c_k))))

    for val, lo, hi in ((q1, -cfg.q1_limit, cfg.q1_limit),
                        (q2, *cfg.q2_range), (q3, *cfg.q3_range)):
        if val < lo:
            viol = max(viol, lo - val)
        elif val > hi:
            viol = max(viol, val - hi)
    q = np.array([
        min(max(q1, -cfg.q1_limit), cfg.q1_limit),
        min(max(q2, cfg.q2_range[0]), cfg.q2_range[1]),
        min(max(q3, cfg.q3_range[0]), cfg.q3_range[1]),
    ])
    return q, viol


# ---- body pose helpers ----------------------------------------------------
def rot(pitch_up: float, yaw: float) -> np.ndarray:
    """Body->world rotation. Positive pitch is nose up (MuJoCo's +y rotation
    is nose down, hence the sign)."""
    cp, sp = math.cos(-pitch_up), math.sin(-pitch_up)
    cy, sy = math.cos(yaw), math.sin(yaw)
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return rz @ ry


def to_world(p_body, body_p, pitch_up, yaw):
    return np.asarray(body_p) + rot(pitch_up, yaw) @ np.asarray(p_body)


def to_body(p_world, body_p, pitch_up, yaw):
    return rot(pitch_up, yaw).T @ (np.asarray(p_world) - np.asarray(body_p))
