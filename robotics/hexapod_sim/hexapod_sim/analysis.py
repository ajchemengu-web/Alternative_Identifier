"""Physics-free checks of a script: IK reach, joint limits, tipping margin."""
from __future__ import annotations

import numpy as np

from .choreo import BodyPose, Choreographer
from .config import RobotConfig
from .kinematics import LEGS, ik, leg_geometries
from .plans import rover_stance_body


def support_margin(planted_xy: np.ndarray, com_xy: np.ndarray) -> float:
    """Signed distance from the CoM to the support polygon edge (m).
    Positive = inside. Uses the convex hull of planted foot positions."""
    pts = np.asarray(planted_xy)
    if len(pts) < 3:
        return -1.0
    # convex hull (monotone chain)
    P = sorted(map(tuple, pts))
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in P:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(P):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    best = np.inf
    for i in range(len(hull)):
        a, b = np.array(hull[i]), np.array(hull[(i + 1) % len(hull)])
        e = b - a
        n = np.linalg.norm(e)
        if n < 1e-9:
            continue
        best = min(best, (e[0] * (com_xy[1] - a[1]) - e[1] * (com_xy[0] - a[0])) / n)
    return float(best)


def dry_run(cfg: RobotConfig, phases, body0: BodyPose, feet0: dict, dt=0.05):
    """Step a script without physics. Returns a dict of worst cases."""
    ch = Choreographer(cfg, phases, body0, feet0, rover_stance_body(cfg))
    geo = leg_geometries(cfg)
    t = 0.0
    worst_v, where_v = 0.0, ""
    qmin = np.full((6, 3), np.inf)
    qmax = np.full((6, 3), -np.inf)
    min_margin, where_m = np.inf, ""
    while not ch.done:
        ch.update(t)
        if ch.done:
            break
        tg = ch.foot_targets_body()
        for i, leg in enumerate(LEGS):
            q, v = ik(cfg, geo[leg], tg[leg])
            qmin[i] = np.minimum(qmin[i], q)
            qmax[i] = np.maximum(qmax[i], q)
            if v > worst_v:
                worst_v, where_v = v, f"{ch.phase_name} / {leg} @ t={t:.1f}"
        planted = [ch.feet[l][:2] for l in LEGS if l not in ch.swinging]
        m = support_margin(np.array(planted), ch.body.p[:2])
        if m < min_margin:
            min_margin, where_m = m, f"{ch.phase_name} @ t={t:.1f}"
        t += dt
    return dict(duration=t, worst_violation=worst_v, where_violation=where_v,
                min_support_margin=min_margin, where_margin=where_m,
                q_min=qmin, q_max=qmax)
