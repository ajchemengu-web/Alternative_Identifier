"""End-to-end missions: the 'home rover meets the staircase' scenario and the
rover-vs-spider energy comparison."""
from __future__ import annotations

import math
import numpy as np

from .choreo import BodyPose, Phase
from .config import RobotConfig, StairConfig
from .metrics import cost_of_transport, energy
from .plans import StairClimber, stair_climb, to_rover, to_spider
from .sim import HexapodSim


def full_mission(cfg=None, stairs=None, video=None, verbose=True,
                 start=(0.0, 0.0, 0.0)):
    cfg, stairs = cfg or RobotConfig(), stairs or StairConfig()
    sim = HexapodSim(cfg, stairs)
    if video:
        sim.enable_video()
    say = print if verbose else (lambda *a, **k: None)
    sim.reset_rover(*start)
    marks = {}

    def stage(name, phases, **kw):
        i0 = len(sim.log.t)
        ok = sim.run(phases, **kw)
        marks[name] = (i0, len(sim.log.t))
        say(f"  [{sim.data.time:6.1f}s] {name}: {'ok' if ok else 'FAILED'}")
        return ok

    x_trans = stairs.x0 - 0.45
    ok = stage("settle", [Phase("settle", 1.0)])
    ok = ok and stage("drive to stairs", [Phase(
        "drive to stairs", 30.0, drive=(0.30, 0.0),
        until=lambda s: s["p"][0] >= x_trans)])
    ok = ok and stage("brake", [Phase("brake", 1.0)])
    ok = ok and stage("rover->spider", to_spider(cfg, sim.ch.body))
    if ok:
        ok = stage("climb stairs", StairClimber(
            cfg, stairs, x_goal=stairs.landing_x + 0.35))
    ok = ok and stage("spider->rover (top)", to_rover(cfg, sim.ch.body,
                                                      ground=stairs.top_height))
    x_end = sim.state()["p"][0] + 0.35
    ok = ok and stage("drive away", [Phase(
        "drive away", 20.0, drive=(0.25, 0.0),
        until=lambda s: s["p"][0] >= x_end)])
    ok = ok and stage("settle (end)", [Phase("settle", 1.0)])
    return sim, marks, ok


def summarize(sim: HexapodSim, marks: dict, ok: bool) -> dict:
    cfg, st = sim.cfg, sim.stairs
    L = sim.log.arrays()
    fin = sim.state()
    tau = np.abs(L["tau"]).reshape(len(L["t"]), 6, 3)
    peak = tau.max((0, 1))
    i0, i1 = marks.get("climb stairs", (0, 0))
    e_climb = energy(L, i0, i1)
    rise = st.top_height
    climb_dist = float(L["p"][i1 - 1, 0] - L["p"][i0, 0]) if i1 > i0 else 0.0
    return dict(
        success=bool(ok and abs(fin["p"][2] - (rise + cfg.rover_height)) < 0.03
                     and fin["p"][0] > st.landing_x + 0.5),
        total_time_s=float(L["t"][-1]),
        final_position_m=[round(float(v), 3) for v in fin["p"]],
        expected_final_z_m=rise + cfg.rover_height,
        peak_torque_Nm=dict(coxa=round(float(peak[0]), 2),
                            femur=round(float(peak[1]), 2),
                            tibia=round(float(peak[2]), 2)),
        torque_limit_Nm=cfg.servo_torque_limit,
        max_roll_deg=round(math.degrees(float(np.abs(L["rpy"][:, 0]).max())), 1),
        max_pitch_deg=round(math.degrees(float(np.abs(L["rpy"][:, 1]).max())), 1),
        max_lateral_drift_m=round(float(np.abs(L["p"][:, 1]).max()), 3),
        ik_violations=int((L["ik_viol"] > 1e-3).sum()),
        self_collisions={" x ".join(k): dict(t=round(v[0], 1), depth_mm=round(v[1] * 1e3, 1))
                         for k, v in sim.self_contacts.items()},
        body_strikes={" x ".join(k): dict(t=round(v[0], 1), depth_mm=round(v[1] * 1e3, 1))
                      for k, v in sim.strikes.items()},
        climb=dict(duration_s=round(e_climb["dt"], 1),
                   mech_J=round(e_climb["mech_J"], 1),
                   elec_J=round(e_climb["elec_J"], 1),
                   cot_electrical=round(cost_of_transport(
                       e_climb["elec_J"], cfg.total_mass, rise), 2)),
        stages={k: dict(start_s=round(float(L["t"][a]), 1),
                        end_s=round(float(L["t"][b - 1]), 1))
                for k, (a, b) in marks.items() if b > a},
        events=sim.events,
    )


def rover_vs_spider(cfg=None, dist=1.0):
    """Same robot, same flat floor: energy per metre rolling vs walking."""
    cfg = cfg or RobotConfig()
    flat = StairConfig(x0=1e3, n_steps=0)
    out = {}
    # rolling
    s = HexapodSim(cfg, flat)
    s.reset_rover(0, 0)
    s.run([Phase("settle", 1.0)])
    i0 = len(s.log.t)
    x0 = s.state()["p"][0]
    s.run([Phase("drive", 20.0, drive=(0.30, 0.0),
                 until=lambda st: st["p"][0] >= x0 + dist)])
    L = s.log.arrays()
    e = energy(L, i0, len(L["t"]))
    d = float(L["p"][-1, 0] - L["p"][i0, 0])
    out["rover"] = dict(dist_m=round(d, 2), time_s=round(e["dt"], 1),
                        elec_J=round(e["elec_J"], 1),
                        cot=round(cost_of_transport(e["elec_J"], cfg.total_mass, d), 2))
    # walking
    s = HexapodSim(cfg, flat)
    s.reset_rover(0, 0)
    s.run([Phase("settle", 0.5)])
    s.run(to_spider(cfg, s.ch.body))
    i0 = len(s.log.t)
    x0 = s.ch.body.p[0]
    plan, _, _ = stair_climb(cfg, flat, s.ch.body, s.ch.feet, x_goal=x0 + dist)
    s.run(plan)
    L = s.log.arrays()
    e = energy(L, i0, len(L["t"]))
    d = float(L["p"][-1, 0] - L["p"][i0, 0])
    out["spider"] = dict(dist_m=round(d, 2), time_s=round(e["dt"], 1),
                         elec_J=round(e["elec_J"], 1),
                         cot=round(cost_of_transport(e["elec_J"], cfg.total_mass, d), 2))
    # one-off cost of changing shape
    s = HexapodSim(cfg, flat)
    s.reset_rover(0, 0)
    s.run([Phase("settle", 0.5)])
    i0 = len(s.log.t)
    s.run(to_spider(cfg, s.ch.body))
    L = s.log.arrays()
    e = energy(L, i0, len(L["t"]))
    out["transform_rover_to_spider"] = dict(time_s=round(e["dt"], 1),
                                            elec_J=round(e["elec_J"], 1))
    return out
