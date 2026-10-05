"""Poses and scripts: stances, rover<->spider transformation, stair gait."""
from __future__ import annotations

import math

import numpy as np

from .choreo import BodyPose, Phase, Swing
from .config import RobotConfig, StairConfig
from .kinematics import (LEGS, MID_LEGS, TRIPOD_A, TRIPOD_B, WHEEL_LEGS,
                         leg_geometries, to_world, rot)


def foot_radius(cfg: RobotConfig, leg: str) -> float:
    return cfg.wheel_radius if leg in WHEEL_LEGS else cfg.foot_radius


def rover_stance_body(cfg: RobotConfig, h=None) -> dict:
    """Body-frame foot targets in rover mode: wheels folded under the hips
    (front ones forward, rear ones aft), middle legs stowed beside the body."""
    h = cfg.rover_height if h is None else h
    out = {}
    for leg, g in leg_geometries(cfg).items():
        if g.has_wheel:
            sx = 1 if g.row == "F" else -1
            out[leg] = np.array([g.hip[0] + sx * cfg.rover_wheel_reach,
                                 g.hip[1], -h + cfg.wheel_radius])
        else:
            out[leg] = np.array([0.0, g.side * (cfg.hip_y + 0.12 * cfg.scale),
                                 -0.05 * cfg.scale])
    return out


def spider_stance_body(cfg: RobotConfig, h=None) -> dict:
    h = cfg.spider_height if h is None else h
    out = {}
    for leg, g in leg_geometries(cfg).items():
        x = {"F": cfg.spider_row_x, "M": 0.0, "R": -cfg.spider_row_x}[g.row]
        y = cfg.spider_mid_y if g.row == "M" else cfg.spider_row_y
        out[leg] = np.array([x, g.side * y, -h + foot_radius(cfg, leg)])
    return out


def world_feet(stance_body: dict, body: BodyPose) -> dict:
    return {k: to_world(v, body.p, body.pitch, body.yaw)
            for k, v in stance_body.items()}


def _flat_target(cfg, stance, leg, body_xy_yaw: BodyPose, ground=0.0):
    """World foot target on flat ground (at height `ground`) for a body-frame
    stance entry."""
    w = to_world(stance[leg], np.array([body_xy_yaw.p[0], body_xy_yaw.p[1], 0.0]),
                 0.0, body_xy_yaw.yaw)
    w[2] = ground + foot_radius(cfg, leg)
    return w


# ---------------------------------------------------------------------------
def to_spider(cfg: RobotConfig, body: BodyPose, t=1.0, ground=0.0) -> list:
    """Rover -> spider on flat ground. At most two corner wheels are ever
    lifted, so >=4 feet are always planted."""
    spider = spider_stance_body(cfg)
    z_mid = ground + 0.5 * (cfg.rover_height + cfg.spider_height)
    mid = BodyPose(np.array([body.p[0], body.p[1], z_mid]), 0.0, body.yaw)
    top = BodyPose(np.array([body.p[0], body.p[1], ground + cfg.spider_height]),
                   0.0, body.yaw)
    tgt = lambda leg: _flat_target(cfg, spider, leg, body, ground)
    return [
        Phase("deploy middle legs", 2.5 * t,
              swings={l: Swing(tgt(l), 0.0) for l in MID_LEGS}),
        Phase("raise body (1/2)", 2.0 * t, body=mid),
        Phase("swing left wheels out", 3.0 * t,
              swings={l: Swing(tgt(l), 0.06 * cfg.scale) for l in ("FL", "RL")}),
        Phase("swing right wheels out", 3.0 * t,
              swings={l: Swing(tgt(l), 0.06 * cfg.scale) for l in ("FR", "RR")}),
        Phase("raise body (2/2)", 2.5 * t, body=top),
    ]


def to_rover(cfg: RobotConfig, body: BodyPose, t=1.0, ground=0.0) -> list:
    """Spider -> rover on flat ground (reverse of `to_spider`)."""
    rover = rover_stance_body(cfg)
    z_mid = ground + 0.5 * (cfg.rover_height + cfg.spider_height)
    mid = BodyPose(np.array([body.p[0], body.p[1], z_mid]), 0.0, body.yaw)
    low = BodyPose(np.array([body.p[0], body.p[1], ground + cfg.rover_height]),
                   0.0, body.yaw)

    def tgt(leg, b):  # wheel centre on the ground at the rover stance
        return _flat_target(cfg, rover, leg, b, ground)

    def tuck(leg):  # stowed foot is above ground: use the rover-height pose
        return to_world(rover[leg], low.p, 0.0, low.yaw)
    return [
        Phase("lower body (1/2)", 2.0 * t, body=mid),
        Phase("swing left wheels in", 3.0 * t,
              swings={l: Swing(tgt(l, low), 0.06 * cfg.scale) for l in ("FL", "RL")}),
        Phase("swing right wheels in", 3.0 * t,
              swings={l: Swing(tgt(l, low), 0.06 * cfg.scale) for l in ("FR", "RR")}),
        Phase("lower body (2/2)", 2.5 * t, body=low),
        Phase("stow middle legs", 2.5 * t,
              swings={l: Swing(tuck(l), 0.0) for l in MID_LEGS}),
    ]


# ---------------------------------------------------------------------------
# Stair climbing: statically stable alternating-tripod gait with footholds
# chosen from the staircase geometry (stand-in for a depth camera).
# ---------------------------------------------------------------------------
def fit_body_pose(cfg: RobotConfig, feet: dict, x_body: float, y_body: float,
                  pitch_limit: float) -> BodyPose:
    """Body pose that sits `spider_height` above the plane through the
    contact points of all six feet (least-squares line in x-z)."""
    xs = np.array([w[0] for w in feet.values()])
    zs = np.array([w[2] - foot_radius(cfg, k) for k, w in feet.items()])
    if np.ptp(xs) < 1e-6:
        slope, z0 = 0.0, zs.mean()
    else:
        slope, z0 = np.polyfit(xs - x_body, zs, 1)
    pitch = float(np.clip(math.atan(slope), -pitch_limit, pitch_limit))
    z = z0 + cfg.spider_height / math.cos(pitch)
    return BodyPose(np.array([x_body, y_body, z]), pitch, 0.0)


def _half_cycle(cfg, st, body, feet, h, dx, half_time, pitch_limit, lift,
                gain=0.0):
    """Plan one half-cycle (one tripod swings, body shifts forward).

    `gain` pulls the commanded lateral offset and heading toward the
    staircase centreline (0 = open loop)."""
    spider = spider_stance_body(cfg)
    group = TRIPOD_A if h % 2 == 0 else TRIPOD_B
    # First shift is half length so the CoM never nears the edge of the
    # 3-leg support triangle while the gait spins up.
    step = dx / 2 if h == 0 else dx
    yaw = body.yaw * (1 - gain)
    y_next = body.p[1] * (1 - gain)
    x_next = body.p[0] + step * math.cos(yaw)
    c, sn = math.cos(yaw), math.sin(yaw)
    swings = {}
    for leg in group:
        nx, ny = spider[leg][0] + dx / 2, spider[leg][1]
        xt = st.valid_foothold(x_next + c * nx - sn * ny,
                               foot_radius(cfg, leg) + 0.02 * cfg.scale)
        yt = y_next + sn * nx + c * ny
        swings[leg] = Swing(np.array([xt, yt, st.height_at(xt)
                                      + foot_radius(cfg, leg)]), lift)
    future = {**feet, **{l: s_.target for l, s_ in swings.items()}}
    nxt = fit_body_pose(cfg, future, x_next, y_next, pitch_limit)
    nxt.yaw = yaw
    phase = Phase(f"step {h + 1}: {'/'.join(group)}", half_time,
                  body=nxt, swings=swings)
    return phase, nxt, future


def _finished(cfg, st, body, feet, h, x_goal):
    on_top = all(abs(w[2] - foot_radius(cfg, k) - st.top_height) < 1e-3
                 for k, w in feet.items())
    return body.p[0] >= x_goal and on_top and h % 2 == 0


def stair_climb(cfg: RobotConfig, st: StairConfig, body: BodyPose, feet: dict,
                x_goal: float, stride: float | None = None,
                half_time: float = 2.0, pitch_limit: float = 0.6,
                lift: float | None = None):
    """Open-loop alternating-tripod crawl from the current spider stance to
    x_goal (used for offline checks). Returns (phases, final_body, final_feet)."""
    lift = 0.06 * cfg.scale if lift is None else lift
    dx = (st.tread if stride is None else stride) / 2
    feet = {k: np.array(v, float) for k, v in feet.items()}
    body = body.copy()
    phases, h = [], 0
    while True:
        ph, body, feet = _half_cycle(cfg, st, body, feet, h, dx, half_time,
                                     pitch_limit, lift)
        phases.append(ph)
        h += 1
        if _finished(cfg, st, body, feet, h, x_goal):
            return phases, body, feet
        if h > 60:
            raise RuntimeError("stair plan did not converge")


class StairClimber:
    """Closed-loop version: one half-cycle is planned at a time from the
    measured pose, correcting lateral drift and heading."""

    def __init__(self, cfg, st, x_goal, stride=None, half_time=2.0,
                 pitch_limit=0.6, lift=None, gain=0.5):
        self.cfg, self.st, self.x_goal = cfg, st, x_goal
        self.dx = (st.tread if stride is None else stride) / 2
        self.half_time, self.pitch_limit = half_time, pitch_limit
        self.lift = 0.06 * cfg.scale if lift is None else lift
        self.gain = gain
        self.h = 0

    def next_phase(self, ch, state):
        if self.h > 0 and _finished(self.cfg, self.st, ch.body, ch.feet,
                                    self.h, self.x_goal):
            return None
        if self.h > 60:
            raise RuntimeError("stair climb did not converge")
        ph, _, _ = _half_cycle(self.cfg, self.st, ch.body, ch.feet, self.h,
                               self.dx, self.half_time, self.pitch_limit,
                               self.lift, self.gain)
        self.h += 1
        return ph
