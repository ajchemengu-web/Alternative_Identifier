"""All design parameters in one place (SI units: m, kg, rad, N*m)."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import math


@dataclass(frozen=True)
class RobotConfig:
    scale: float = 1.0                       # 1.0 = reference design (see scaled())

    # --- torso -----------------------------------------------------------
    torso_half: tuple = (0.20, 0.09, 0.03)   # half extents of the body box
    torso_mass: float = 2.6                  # battery + electronics + frame
    hip_x: float = 0.15                      # front/rear hip distance from centre
    hip_y: float = 0.12                      # hip offset from centre line

    # --- leg links (coxa yaw -> femur pitch -> tibia pitch) ---------------
    coxa: float = 0.04
    femur: float = 0.20
    tibia: float = 0.24
    coxa_mass: float = 0.12                  # servo + bracket
    femur_mass: float = 0.17
    tibia_mass: float = 0.14
    link_radius: float = 0.012

    # --- wheels (on the 4 corner legs) and plain feet (2 middle legs) -----
    wheel_radius: float = 0.05
    wheel_width: float = 0.04
    wheel_mass: float = 0.15
    foot_radius: float = 0.02
    foot_mass: float = 0.03

    # --- joint limits (rad) ----------------------------------------------
    q1_limit: float = 1.80
    q2_range: tuple = (-0.90, 2.40)          # femur, positive = up
    q3_range: tuple = (-2.90, 0.20)          # tibia, negative = knee bent

    # --- actuators --------------------------------------------------------
    servo_kp: float = 80.0                   # N*m/rad
    servo_kv: float = 2.0                    # N*m*s/rad
    servo_torque_limit: float = 10.0         # N*m, peak (see report for need)
    wheel_kp: float = 20.0
    wheel_kv: float = 0.6
    wheel_torque_limit: float = 3.0

    # --- poses ------------------------------------------------------------
    rover_height: float = 0.14               # body centre height, rover mode
    spider_height: float = 0.20              # body centre height, spider mode
    rover_wheel_reach: float = 0.08          # wheel offset fwd/aft of its hip
    spider_row_x: float = 0.25               # front/rear foot row, body frame
    spider_row_y: float = 0.26               # front/rear foot lateral
    spider_mid_y: float = 0.28               # middle foot lateral

    # --- friction ---------------------------------------------------------
    foot_friction: float = 1.0
    wheel_friction: float = 1.2

    @property
    def total_mass(self) -> float:
        links = 6 * (self.coxa_mass + self.femur_mass + self.tibia_mass)
        return (self.torso_mass + links + 4 * self.wheel_mass
                + 2 * self.foot_mass)


@dataclass(frozen=True)
class StairConfig:
    """A straight home staircase followed by a landing."""
    x0: float = 1.20          # world x of the first riser
    rise: float = 0.18
    tread: float = 0.26
    n_steps: int = 4
    width: float = 0.90
    landing: float = 1.50     # depth of the landing after the last riser

    @property
    def slope(self) -> float:
        return math.atan2(self.rise, self.tread)

    @property
    def top_height(self) -> float:
        return self.n_steps * self.rise

    @property
    def landing_x(self) -> float:
        """World x where the top landing begins (last riser)."""
        return self.x0 + (self.n_steps - 1) * self.tread

    def height_at(self, x: float) -> float:
        if x < self.x0:
            return 0.0
        k = int((x - self.x0) // self.tread) + 1
        return min(k, self.n_steps) * self.rise

    def valid_foothold(self, x: float, margin: float) -> float:
        """Snap x to the nearest point at least `margin` from any step edge
        (the stand-in for a depth camera picking safe footholds)."""
        edges = [self.x0 + i * self.tread for i in range(self.n_steps)]
        for e in edges:
            if abs(x - e) < margin:
                # push to whichever side is closer (above or below the edge)
                x = e + margin if x >= e else e - margin
        return x


def scaled(cfg: RobotConfig, st: StairConfig, k: float):
    """Geometrically scaled copy of the design and of the staircase.

    Lengths scale by k, masses by k^3 (same density), torques/gains by k^4.
    NOTE: real actuators do not shrink with k^3, so the true mass of a small
    robot is higher than this ideal; use `mass_factor` runs to bound that."""
    c = cfg
    c = replace(
        c, scale=c.scale * k,
        torso_half=tuple(v * k for v in c.torso_half), torso_mass=c.torso_mass * k**3,
        hip_x=c.hip_x * k, hip_y=c.hip_y * k,
        coxa=c.coxa * k, femur=c.femur * k, tibia=c.tibia * k,
        coxa_mass=c.coxa_mass * k**3, femur_mass=c.femur_mass * k**3,
        tibia_mass=c.tibia_mass * k**3, link_radius=c.link_radius * k,
        wheel_radius=c.wheel_radius * k, wheel_width=c.wheel_width * k,
        wheel_mass=c.wheel_mass * k**3, foot_radius=c.foot_radius * k,
        foot_mass=c.foot_mass * k**3,
        servo_kp=c.servo_kp * k**4, servo_kv=c.servo_kv * k**4,
        servo_torque_limit=c.servo_torque_limit * k**4,
        wheel_kp=c.wheel_kp * k**4, wheel_kv=c.wheel_kv * k**4,
        wheel_torque_limit=c.wheel_torque_limit * k**4,
        rover_height=c.rover_height * k, spider_height=c.spider_height * k,
        rover_wheel_reach=c.rover_wheel_reach * k,
        spider_row_x=c.spider_row_x * k, spider_row_y=c.spider_row_y * k,
        spider_mid_y=c.spider_mid_y * k)
    t = replace(st, x0=st.x0 * k, rise=st.rise * k, tread=st.tread * k,
                width=st.width * k, landing=st.landing * k)
    return c, t
