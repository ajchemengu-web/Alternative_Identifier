#!/usr/bin/env python3
"""Design sweeps: how much servo torque is needed, and which staircases the
current leg geometry can climb. Writes results/sweeps.json."""
import argparse
import json
import math
import os
import random
from dataclasses import replace

from hexapod_sim.config import RobotConfig, StairConfig
from hexapod_sim.mission import full_mission, summarize


def run(cfg, st):
    try:
        sim, marks, ok = full_mission(cfg, st, verbose=False)
        s = summarize(sim, marks, ok)
        return dict(success=s["success"], peak_torque=s["peak_torque_Nm"],
                    fell=bool(sim.events), ik_violations=s["ik_violations"],
                    max_pitch_deg=s["max_pitch_deg"], max_roll_deg=s["max_roll_deg"])
    except Exception as e:  # planner could not reach the footholds
        return dict(success=False, error=str(e)[:80])


def robustness(n, seed=0):
    """Randomised trials: friction, payload mass, start offset and heading."""
    rng = random.Random(seed)
    base, st = RobotConfig(), StairConfig()
    trials = []
    for i in range(n):
        f = rng.uniform(0.7, 1.3)
        cfg = replace(base, foot_friction=base.foot_friction * f,
                      wheel_friction=base.wheel_friction * f,
                      torso_mass=base.torso_mass * rng.uniform(0.85, 1.25))
        start = (0.0, rng.uniform(-0.05, 0.05), math.radians(rng.uniform(-3, 3)))
        sim, marks, ok = full_mission(cfg, st, verbose=False, start=start)
        s = summarize(sim, marks, ok)
        trials.append(dict(friction_scale=round(f, 2),
                           torso_mass=round(cfg.torso_mass, 2),
                           start_y=round(start[1], 3),
                           start_yaw_deg=round(math.degrees(start[2]), 1),
                           success=s["success"], fell=bool(sim.events),
                           peak_femur=s["peak_torque_Nm"]["femur"],
                           max_pitch_deg=s["max_pitch_deg"],
                           max_drift_m=s["max_lateral_drift_m"]))
        print(f"  trial {i + 1:2d}: {'OK ' if s['success'] else 'FAIL'} {trials[-1]}")
    wins = sum(t["success"] for t in trials)
    print(f"robustness: {wins}/{n} successful")
    return dict(n=n, successes=wins, trials=trials)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--robust", type=int, default=0,
                    help="run N randomised trials instead of the sweeps")
    a = ap.parse_args()
    if a.robust:
        os.makedirs("results", exist_ok=True)
        r = robustness(a.robust)
        with open("results/robustness.json", "w") as f:
            json.dump(r, f, indent=2)
        return
    out = {"torque_limit": {}, "stairs": {}}
    base_cfg, base_st = RobotConfig(), StairConfig()
    print("servo torque limit sweep (N*m):")
    for T in (3.0, 4.0, 5.0, 6.0, 8.0):
        r = run(replace(base_cfg, servo_torque_limit=T), base_st)
        out["torque_limit"][str(T)] = r
        print(f"  {T:4.1f} -> {'OK ' if r['success'] else 'FAIL'}  {r}")
    print("staircase sweep (rise x tread, m):")
    for rise in (0.15, 0.18, 0.20, 0.22):
        for tread in (0.22, 0.26, 0.30):
            r = run(base_cfg, replace(base_st, rise=rise, tread=tread))
            out["stairs"][f"rise={rise}, tread={tread}"] = r
            print(f"  rise {rise:.2f} tread {tread:.2f} -> "
                  f"{'OK ' if r['success'] else 'FAIL'} "
                  f"{r.get('error', '')} peak {r.get('peak_torque', '')}")
    os.makedirs("results", exist_ok=True)
    with open("results/sweeps.json", "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
