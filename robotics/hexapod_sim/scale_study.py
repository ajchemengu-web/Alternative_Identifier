#!/usr/bin/env python3
"""How does the actuator requirement shrink with robot size?

Scales the whole design and staircase geometrically (lengths x k, ideal
masses x k^3, torques x k^4), optionally with extra mass because real
actuators do not shrink as fast as the geometry, then runs the full mission
nominally and under randomised friction / payload / start offset / heading.
Writes results/scale_study.json."""
import json
import math
import os
import random
from dataclasses import replace

import numpy as np

from hexapod_sim.config import RobotConfig, StairConfig, scaled
from hexapod_sim.mission import full_mission, summarize

KG_CM = 10.197  # 1 N*m in kg*cm


def heavier(c, f):
    return replace(c, torso_mass=c.torso_mass * f, coxa_mass=c.coxa_mass * f,
                   femur_mass=c.femur_mass * f, tibia_mass=c.tibia_mass * f,
                   wheel_mass=c.wheel_mass * f, foot_mass=c.foot_mass * f)


def build(k, f):
    c, t = scaled(RobotConfig(), StairConfig(), k)
    c = heavier(c, f)
    # generous clamp so we measure demand rather than the limit
    return replace(c, servo_torque_limit=10.0 * k**4 * f * 1.5), t


def main(n_random=15):
    out = []
    print("scale mass_x  kg   rise_cm  nominal  femur N.m (kg.cm)  | random: ok  femur_max (kg.cm)")
    for k, f in ((1.0, 1.0), (0.75, 1), (0.75, 2), (0.6, 1), (0.6, 2), (0.6, 3),
                 (0.5, 1), (0.5, 2), (0.5, 3), (0.4, 2)):
        c, t = build(k, f)
        sim, marks, ok = full_mission(c, t, verbose=False)
        s = summarize(sim, marks, ok)
        rng = random.Random(1)
        wins, fem, pitch = 0, [], []
        for _ in range(n_random):
            fr = rng.uniform(0.7, 1.3)
            cr = replace(c, foot_friction=fr, wheel_friction=1.2 * fr,
                         torso_mass=c.torso_mass * rng.uniform(0.85, 1.25))
            start = (0.0, rng.uniform(-0.05, 0.05) * k,
                     math.radians(rng.uniform(-3, 3)))
            sm, mk, okr = full_mission(cr, t, verbose=False, start=start)
            sr = summarize(sm, mk, okr)
            wins += sr["success"]
            fem.append(sr["peak_torque_Nm"]["femur"])
            pitch.append(sr["max_pitch_deg"])
        row = dict(scale=k, mass_factor=f, robot_kg=round(c.total_mass, 2),
                   rise_cm=round(t.rise * 100, 1), nominal_success=s["success"],
                   femur_Nm=s["peak_torque_Nm"]["femur"],
                   femur_kgcm=round(s["peak_torque_Nm"]["femur"] * KG_CM, 1),
                   random_trials=n_random, random_successes=wins,
                   random_femur_max_Nm=round(max(fem), 2),
                   random_femur_max_kgcm=round(max(fem) * KG_CM, 1),
                   random_max_pitch_deg=round(max(pitch)))
        out.append(row)
        print(f"{k:4.2f}  x{f:<4} {row['robot_kg']:5.2f} {row['rise_cm']:6.1f}   "
              f"{str(row['nominal_success']):5}   {row['femur_Nm']:5.2f} ({row['femur_kgcm']:5.1f})"
              f"      | {wins}/{n_random}   {row['random_femur_max_Nm']:5.2f} "
              f"({row['random_femur_max_kgcm']:5.1f})  pitch<= {row['random_max_pitch_deg']}")
    os.makedirs("results", exist_ok=True)
    with open("results/scale_study.json", "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
