"""Generates the MJCF model (robot + staircase) from the config objects."""
from __future__ import annotations

from .config import RobotConfig, StairConfig
from .kinematics import LEGS, leg_geometries

JOINT_KINDS = ("q1", "q2", "q3")


def _stairs_xml(st: StairConfig) -> str:
    out = []
    for k in range(1, st.n_steps + 1):
        x_start = st.x0 + (k - 1) * st.tread
        depth = st.landing if k == st.n_steps else st.tread
        h = k * st.rise
        out.append(
            f'<geom name="step{k}" type="box" '
            f'pos="{x_start + depth / 2:.4f} 0 {h / 2:.4f}" '
            f'size="{depth / 2:.4f} {st.width / 2:.4f} {h / 2:.4f}" '
            f'rgba="0.62 0.55 0.45 1" friction="0.9 0.01 0.001"/>')
    return "\n    ".join(out)


def _leg_xml(cfg: RobotConfig, name: str) -> str:
    g = leg_geometries(cfg)[name]
    L1, L2, L3, rr = cfg.coxa, cfg.femur, cfg.tibia, cfg.link_radius
    q2lo, q2hi = cfg.q2_range
    q3lo, q3hi = cfg.q3_range
    hx, hy, _ = g.hip
    if g.has_wheel:
        end = (
            f'<body name="{name}_wheel" pos="{L3} 0 0">'
            f'<joint name="{name}_wheel" type="hinge" axis="0 1 0" damping="0.01"/>'
            f'<geom name="{name}_wheel_geom" type="cylinder" '
            f'size="{cfg.wheel_radius} {cfg.wheel_width / 2}" zaxis="0 1 0" '
            f'mass="{cfg.wheel_mass}" friction="{cfg.wheel_friction} 0.02 0.002" '
            f'rgba="0.1 0.1 0.1 1"/></body>')
    else:
        end = (
            f'<geom name="{name}_foot" type="sphere" pos="{L3} 0 0" '
            f'size="{cfg.foot_radius}" mass="{cfg.foot_mass}" '
            f'friction="{cfg.foot_friction} 0.02 0.002" rgba="0.1 0.1 0.1 1"/>')
    return f"""
    <body name="{name}_coxa" pos="{hx} {hy} 0" euler="0 0 {g.mount_yaw}">
      <joint name="{name}_q1" type="hinge" axis="0 0 1"
             range="{-cfg.q1_limit} {cfg.q1_limit}" damping="0.05" armature="0.01"/>
      <geom name="{name}_coxa_geom" type="capsule" fromto="0 0 0 {L1} 0 0"
            size="{rr}" mass="{cfg.coxa_mass}" rgba="0.35 0.35 0.4 1"/>
      <body name="{name}_femur" pos="{L1} 0 0">
        <joint name="{name}_q2" type="hinge" axis="0 -1 0"
               range="{q2lo} {q2hi}" damping="0.05" armature="0.01"/>
        <geom name="{name}_femur_geom" type="capsule" fromto="0 0 0 {L2} 0 0"
              size="{rr}" mass="{cfg.femur_mass}" rgba="0.8 0.3 0.1 1"/>
        <body name="{name}_tibia" pos="{L2} 0 0">
          <joint name="{name}_q3" type="hinge" axis="0 -1 0"
                 range="{q3lo} {q3hi}" damping="0.05" armature="0.01"/>
          <geom name="{name}_tibia_geom" type="capsule" fromto="0 0 0 {L3} 0 0"
                size="{rr * 0.9}" mass="{cfg.tibia_mass}" rgba="0.35 0.35 0.4 1"/>
          {end}
        </body>
      </body>
    </body>"""


def build_xml(cfg: RobotConfig, stairs: StairConfig) -> str:
    hx, hy, hz = cfg.torso_half
    T = cfg.servo_torque_limit
    acts = []
    for leg in LEGS:
        for k in ("q1", "q2", "q3"):
            acts.append(
                f'<position name="{leg}_{k}" joint="{leg}_{k}" kp="{cfg.servo_kp}" '
                f'kv="{cfg.servo_kv}" forcerange="{-T} {T}"/>')
        if leg[0] != "M":
            W = cfg.wheel_torque_limit
            acts.append(
                f'<position name="{leg}_wheel" joint="{leg}_wheel" '
                f'kp="{cfg.wheel_kp}" kv="{cfg.wheel_kv}" forcerange="{-W} {W}"/>')
    legs = "".join(_leg_xml(cfg, n) for n in LEGS)
    return f"""<mujoco model="wheel_legged_hexapod">
  <compiler angle="radian"/>
  <option timestep="0.002" integrator="implicitfast" gravity="0 0 -9.81"/>
  <visual><global offwidth="1280" offheight="720"/>
          <headlight ambient="0.45 0.45 0.45" diffuse="0.6 0.6 0.6"/></visual>
  <asset>
    <texture name="grid" type="2d" builtin="checker" rgb1="0.85 0.87 0.9"
             rgb2="0.78 0.8 0.84" width="256" height="256"/>
    <material name="grid" texture="grid" texrepeat="12 12" reflectance="0.05"/>
  </asset>
  <default>
    <geom solref="0.005 1" solimp="0.95 0.99 0.001" friction="1 0.02 0.002"/>
  </default>
  <worldbody>
    <light pos="1 -1 3" dir="-0.2 0.3 -1" diffuse="0.6 0.6 0.6"/>
    <geom name="ground" type="plane" size="8 8 0.1" material="grid"/>
    {_stairs_xml(stairs)}
    <body name="torso" pos="0 0 {cfg.rover_height + 0.02}">
      <freejoint name="root"/>
      <geom name="torso_geom" type="box" size="{hx} {hy} {hz}"
            mass="{cfg.torso_mass}" rgba="0.15 0.45 0.75 1"/>
      <geom name="head" type="box" pos="{hx - 0.02} 0 {hz + 0.015}"
            size="0.025 0.04 0.015" mass="0.001" contype="0" conaffinity="0"
            rgba="0.9 0.9 0.2 1"/>
      {legs}
    </body>
  </worldbody>
  <actuator>
    {chr(10).join("    " + a for a in acts)}
  </actuator>
</mujoco>"""
