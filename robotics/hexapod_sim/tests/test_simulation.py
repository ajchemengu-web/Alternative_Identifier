"""Physics integration tests (a few seconds each)."""
import math

import numpy as np
import pytest

from hexapod_sim.choreo import Phase
from hexapod_sim.config import RobotConfig, StairConfig
from hexapod_sim.mission import full_mission, summarize
from hexapod_sim.plans import StairClimber, to_rover, to_spider
from hexapod_sim.sim import HexapodSim


def test_rover_pose_is_stable():
    s = HexapodSim()
    s.reset_rover(0, 0)
    assert s.run([Phase("settle", 2.0)])
    st = s.state()
    assert st["p"][2] == pytest.approx(s.cfg.rover_height, abs=0.01)
    assert not s.self_contacts and not s.strikes


def test_transform_roundtrip_is_clean():
    s = HexapodSim()
    s.reset_rover(0, 0)
    s.run([Phase("settle", 0.5)])
    assert s.run(to_spider(s.cfg, s.ch.body))
    assert s.state()["p"][2] == pytest.approx(s.cfg.spider_height, abs=0.01)
    assert s.run(to_rover(s.cfg, s.ch.body))
    assert s.state()["p"][2] == pytest.approx(s.cfg.rover_height, abs=0.01)
    L = s.log.arrays()
    assert not s.self_contacts, s.self_contacts          # no leg/wheel clashes
    assert np.degrees(np.abs(L["rpy"][:, :2]).max()) < 3  # stays level
    assert np.abs(L["tau"]).max() < s.cfg.servo_torque_limit


def test_full_mission_reaches_top_landing():
    sim, marks, ok = full_mission(verbose=False)
    s = summarize(sim, marks, ok)
    assert s["success"], s
    assert s["max_lateral_drift_m"] < 0.08     # stayed on a 0.9 m stair
    assert s["max_roll_deg"] < 5
    assert not sim.events                       # never fell over
    assert not s["self_collisions"]
