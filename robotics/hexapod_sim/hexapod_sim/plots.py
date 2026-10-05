import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def make_plots(sim, marks, path):
    L = sim.log.arrays()
    t = L["t"]
    fig, ax = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    ax[0].plot(t, L["p"][:, 2], label="body height (m)")
    ax[0].plot(t, L["p"][:, 0], label="forward x (m)", alpha=.6)
    ax[0].set_ylabel("m"); ax[0].legend(loc="upper left")
    ax[1].plot(t, np.degrees(L["rpy"][:, 1]), label="pitch")
    ax[1].plot(t, np.degrees(L["rpy"][:, 0]), label="roll")
    ax[1].set_ylabel("deg"); ax[1].legend(loc="upper left")
    tau = np.abs(L["tau"]).reshape(len(t), 6, 3)
    for i, n in enumerate(("coxa (yaw)", "femur", "tibia")):
        ax[2].plot(t, tau[:, :, i].max(1), label=f"peak {n}")
    ax[2].axhline(sim.cfg.servo_torque_limit, color="r", ls="--", lw=.8,
                  label="servo limit")
    ax[2].set_ylabel("N·m"); ax[2].set_xlabel("time (s)")
    ax[2].legend(loc="upper left", ncol=2)
    for name, (a, b) in marks.items():
        if b > a:
            for x in ax:
                x.axvline(t[a], color="k", lw=.4, alpha=.4)
            ax[0].text(t[a], ax[0].get_ylim()[1], name, rotation=90,
                       va="top", ha="right", fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
