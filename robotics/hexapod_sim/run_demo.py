#!/usr/bin/env python3
"""Run the hexapod simulation.

  python run_demo.py                 # full mission, prints a summary
  python run_demo.py --video out.mp4 # also render a video (needs MUJOCO_GL=osmesa/egl headless)
  python run_demo.py --compare       # rover-vs-spider energy comparison
"""
import argparse
import json
import os
import sys

# MuJoCo reads MUJOCO_GL at import time, so choose a headless backend first.
if "--video" in sys.argv:
    os.environ.setdefault("MUJOCO_GL", "osmesa")

from hexapod_sim.mission import full_mission, rover_vs_spider, summarize


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", help="write an mp4 of the mission")
    ap.add_argument("--out", default="results", help="output directory")
    ap.add_argument("--compare", action="store_true",
                    help="rolling vs walking energy on flat ground")
    ap.add_argument("--no-plots", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    print("Mission: rover -> stairs -> spider climb -> rover")
    sim, marks, ok = full_mission(video=a.video)
    summ = summarize(sim, marks, ok)
    if a.compare:
        summ["rover_vs_spider_flat"] = rover_vs_spider()
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump(summ, f, indent=2)
    print(json.dumps(summ, indent=2))
    if not a.no_plots:
        from hexapod_sim.plots import make_plots
        make_plots(sim, marks, os.path.join(a.out, "mission.png"))
    if a.video:
        sim.save_video(a.video)
        print("video:", a.video)
    return 0 if summ["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
