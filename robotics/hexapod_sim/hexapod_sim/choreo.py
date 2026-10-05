"""Choreography engine.

A script is a list of `Phase`s. In a phase the body follows a smooth path to a
target pose while chosen feet "swing" to new world-frame positions; every other
foot stays planted at its world position. Joint targets come from inverse
kinematics of (planted/swinging world foot) -> body frame. The same machinery
runs the transformation and the stair gait.

`Drive` phases are different: the legs hold the rover stance (body frame) and
the wheels roll."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional
import math

import numpy as np

from .config import RobotConfig
from .kinematics import LEGS, WHEEL_LEGS, to_body, to_world


@dataclass
class BodyPose:
    p: np.ndarray
    pitch: float = 0.0   # nose-up positive
    yaw: float = 0.0

    def copy(self) -> "BodyPose":
        return BodyPose(np.array(self.p, float), self.pitch, self.yaw)


@dataclass
class Swing:
    target: np.ndarray
    lift: float = 0.05      # clearance above the higher of start/end


@dataclass
class Phase:
    name: str
    duration: float
    body: Optional[BodyPose] = None          # end pose (None = hold)
    swings: dict = field(default_factory=dict)   # leg -> Swing
    # Drive phases only:
    drive: Optional[tuple] = None            # (speed m/s, yaw-rate rad/s)
    until: Optional[Callable] = None         # state -> bool, ends the drive


def smooth(s: float) -> float:
    s = min(max(s, 0.0), 1.0)
    return s * s * s * (10 + s * (-15 + 6 * s))


def swing_path(p0, p1, lift, s):
    """Lift first, travel horizontally at height, then set down."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    u = smooth((s - 0.25) / 0.5)
    z_peak = max(p0[2], p1[2]) + lift
    if s < 0.35:
        z = p0[2] + (z_peak - p0[2]) * smooth(s / 0.35)
    elif s > 0.65:
        z = z_peak + (p1[2] - z_peak) * smooth((s - 0.65) / 0.35)
    else:
        z = z_peak
    xy = p0[:2] + (p1[:2] - p0[:2]) * u
    return np.array([xy[0], xy[1], z])


class Choreographer:
    def __init__(self, cfg: RobotConfig, phases, body0: BodyPose, feet0: dict,
                 rover_body_feet: dict):
        self.cfg = cfg
        self.queue = list(phases)
        self.body = body0.copy()
        self.feet = {k: np.array(v, float) for k, v in feet0.items()}
        self.rover_body_feet = rover_body_feet
        self.cur: Optional[Phase] = None
        self.t0 = 0.0
        self.mode = "world"          # "world" or "drive"
        self.wheel_cmd = {leg: 0.0 for leg in WHEEL_LEGS}  # rolling rad/s
        self.swinging: set = set()
        self.log: list = []          # (t, phase name) transitions
        self._body_start = None
        self._feet_start = None

    # ------------------------------------------------------------------
    @property
    def done(self) -> bool:
        return self.cur is None and not self.queue

    @property
    def phase_name(self) -> str:
        return self.cur.name if self.cur else "done"

    def _begin(self, t, state):
        self.cur = self.queue.pop(0)
        self.t0 = t
        self.log.append((t, self.cur.name))
        self._body_start = self.body.copy()
        self._feet_start = {k: v.copy() for k, v in self.feet.items()}
        if self.cur.drive is not None:
            self.mode = "drive"

    def _end(self, state):
        ph = self.cur
        if ph.drive is not None:
            # Re-plant the feet in the world from the measured body pose.
            self.mode = "world"
            self.wheel_cmd = {leg: 0.0 for leg in WHEEL_LEGS}
            ground = state.get("ground", 0.0)
            b = BodyPose(np.array([state["p"][0], state["p"][1],
                                   ground + self.cfg.rover_height]),
                         0.0, state["yaw"])
            self.body = b
            for leg, pb in self.rover_body_feet.items():
                w = to_world(pb, b.p, b.pitch, b.yaw)
                r = self.cfg.wheel_radius if leg in WHEEL_LEGS else self.cfg.foot_radius
                if leg in WHEEL_LEGS:
                    w[2] = ground + r
                self.feet[leg] = w
        else:
            if ph.body is not None:
                self.body = ph.body.copy()
            for leg, sw in ph.swings.items():
                self.feet[leg] = np.array(sw.target, float)
        self.swinging = set()
        self.cur = None

    # ------------------------------------------------------------------
    def update(self, t: float, state: Optional[dict] = None):
        """Advance the script to time t. `state` (measured body pose) is only
        required for Drive phases."""
        while True:
            if self.cur is None:
                if not self.queue:
                    return
                self._begin(t, state)
            ph = self.cur
            elapsed = t - self.t0
            if ph.drive is not None:
                ended = elapsed >= ph.duration or (
                    ph.until is not None and state is not None and ph.until(state))
                if ended:
                    self._end(state)
                    continue
                v, w = ph.drive
                R, half = self.cfg.wheel_radius, self.cfg.hip_y
                ramp = min(1.0, elapsed / 0.5)
                for leg in WHEEL_LEGS:
                    side = 1 if leg[1] == "L" else -1
                    self.wheel_cmd[leg] = ramp * (v - side * w * half) / R
                return
            s = elapsed / ph.duration if ph.duration > 0 else 1.0
            if s >= 1.0:
                self._end(state)
                continue
            e = smooth(s)
            if ph.body is not None:
                b0, b1 = self._body_start, ph.body
                self.body = BodyPose(b0.p + (b1.p - b0.p) * e,
                                     b0.pitch + (b1.pitch - b0.pitch) * e,
                                     b0.yaw + (b1.yaw - b0.yaw) * e)
            self.swinging = set(ph.swings)
            for leg, sw in ph.swings.items():
                self.feet[leg] = swing_path(self._feet_start[leg], sw.target,
                                            sw.lift, s)
            return

    def resync(self, state: dict):
        """Between phases: take the measured planar pose and the measured
        planted-foot positions as the new reference (closes the loop on
        slip). Heights/pitch keep following the plan."""
        self.body.p[:2] = state["p"][:2]
        self.body.yaw = state["yaw"]
        for leg, xy in state["foot_xy"].items():
            self.feet[leg][:2] = xy

    # ------------------------------------------------------------------
    def foot_targets_body(self) -> dict:
        if self.mode == "drive":
            return {k: np.array(v) for k, v in self.rover_body_feet.items()}
        return {leg: to_body(w, self.body.p, self.body.pitch, self.body.yaw)
                for leg, w in self.feet.items()}
