import math
import numpy as np
import pytest

from hexapod_sim.config import RobotConfig
from hexapod_sim.kinematics import (LEGS, fk, ik, leg_geometries, to_body,
                                    to_world)

CFG = RobotConfig()
GEO = leg_geometries(CFG)


@pytest.mark.parametrize("name", LEGS)
def test_fk_ik_roundtrip(name):
    leg = GEO[name]
    for q in ([0.0, 0.3, -1.6], [-0.5, 0.1, -1.2], [0.4, 0.6, -1.9]):
        p = fk(CFG, leg, q)
        q2, viol = ik(CFG, leg, p)
        assert viol == 0.0
        assert np.allclose(fk(CFG, leg, q2), p, atol=1e-9)


def test_unreachable_is_flagged():
    q, viol = ik(CFG, GEO["FL"], [5, 5, -5])
    assert viol > 0.5


def test_body_pose_roundtrip():
    p = np.array([0.3, -0.1, 0.2])
    w = to_world(p, [1, 2, 3], 0.4, 0.7)
    assert np.allclose(to_body(w, [1, 2, 3], 0.4, 0.7), p)


def test_nose_up_raises_front():
    front = to_world([0.2, 0, 0], [0, 0, 0], math.radians(20), 0)
    assert front[2] > 0.05
