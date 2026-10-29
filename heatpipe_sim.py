#!/usr/bin/env python3
"""
heatpipe_sim.py - 1-D transient two-phase heat pipe simulator for space
reactor / microgravity applications (liquid-metal, wick-driven, sodium default).

WHAT IT MODELS
--------------
* Axial nodal model: evaporator | adiabatic | condenser, one lumped
  "wall + liquid-saturated wick" temperature per node.
* Two-phase closure: at every node, interfacial phase change
      mdot_i = G_i (Tw_i - Tv) / hfg
  where 1/G_i = radial conduction (wall + saturated wick, Chi's sintered-powder
  k_eff) + Schrage kinetic interface resistance.  Quasi-steady vapor: the vapor
  temperature Tv is solved each step so total evaporation = total condensation.
* Operating-limit enforcement every instant, using the actual vapor temperature:
  capillary (with gravity/acceleration term; ZERO in microgravity), sonic,
  viscous, entrainment, nucleate-boiling.  Evaporation is smoothly capped by
  the weakest limit -> dryout / hot-spot behavior emerges when exceeded.
* Condenser boundary: thermal radiation to space (radiator) and/or convective
  heat exchanger (e.g. Stirling / Brayton converter interface).
* Post-processing: vapor / liquid / capillary pressure profiles and margins.

KEY SIMPLIFICATIONS (read before trusting numbers)
--------------------------------------------------
* Continuum vapor flow only. Frozen-start (T < ~600 K for sodium, free-molecular
  vapor, melt-front tracking) is NOT modeled; start from T_init >= ~850-900 K (colder starts stall: continuum vapor limit ~ 0).
  The sonic/viscous limits do capture the low-temperature vapor-limited regime.
* Wick assumed saturated; liquid inventory / pooling / priming in microgravity
  is not tracked (a well-charged, fully primed pipe is assumed).
* Uniform vapor pressure in the closure; pressure profiles are diagnostics.
* Sensible heat of liquid return flow and non-condensable gas are neglected.
* Property correlations are for sodium (Fink & Leibowitz-type fits). To use
  another fluid, subclass `Sodium` and override the property methods.

This is an engineering/educational tool, not a qualified design code.

Usage:
    python heatpipe_sim.py                       # nominal micro-g startup demo
    python heatpipe_sim.py --g 9.81 --power 1500 # ground test, evaporator-up
    python heatpipe_sim.py --limits-only
"""
from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass, field

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

R_GAS = 8.314462618       # J/mol/K
SIGMA_SB = 5.670374419e-8  # W/m^2/K^4
G0 = 9.80665               # m/s^2

LIMIT_NAMES = ["capillary", "sonic", "viscous", "entrainment", "boiling"]


# ----------------------------------------------------------------------------
# Working fluid
# ----------------------------------------------------------------------------
class Sodium:
    """Saturated sodium properties (SI). Valid roughly 600-1500 K."""
    name = "sodium"
    M = 0.02298977      # kg/mol
    Tc = 2503.7         # K
    T_melt = 370.98     # K

    @staticmethod
    def _c(T):
        return np.clip(np.asarray(T, dtype=float), 380.0, 2400.0)

    def Psat(self, T):                      # Pa
        T = self._c(T)
        return 1e6 * np.exp(11.9463 - 12633.73 / T - 0.4672 * np.log(T))

    def hfg(self, T):                       # J/kg
        x = 1.0 - self._c(T) / self.Tc
        return 1e3 * (393.37 * x + 4398.6 * x ** 0.29302)

    def rho_l(self, T):                     # kg/m3
        x = 1.0 - self._c(T) / self.Tc
        return 219.0 + 275.32 * x + 511.58 * np.sqrt(x)

    def sigma(self, T):                     # N/m
        return 0.2402 * (1.0 - self._c(T) / self.Tc) ** 1.126

    def mu_l(self, T):                      # Pa s
        T = self._c(T)
        return np.exp(-6.4406 - 0.3958 * np.log(T) + 556.835 / T)

    def k_l(self, T):                       # W/m/K
        T = self._c(T)
        return 124.67 - 0.11381 * T + 5.5226e-5 * T ** 2 - 1.1842e-8 * T ** 3

    def cp_l(self, T):                      # J/kg/K
        T = self._c(T)
        return 1e3 * (1.6582 - 8.4790e-4 * T + 4.4541e-7 * T ** 2)

    def mu_v(self, T):                      # Pa s
        return 6.083e-9 * self._c(T) + 1.2606e-5

    def rho_v(self, T):                     # kg/m3 (ideal gas at Psat)
        T = self._c(T)
        return self.Psat(T) * self.M / (R_GAS * T)

    def h_interface(self, T, alpha=1.0):
        """Schrage kinetic evaporation/condensation coefficient, W/m2/K."""
        T = self._c(T)
        return ((2 * alpha / (2 - alpha)) * self.hfg(T) ** 2 * self.rho_v(T) / T
                * np.sqrt(self.M / (2 * np.pi * R_GAS * T)))


# ----------------------------------------------------------------------------
# Wick and heat pipe geometry
# ----------------------------------------------------------------------------
@dataclass
class Wick:
    thickness: float          # m
    porosity: float           # -
    r_eff: float              # effective capillary pore radius, m
    permeability: float       # m^2
    k_solid: float = 22.0     # W/m/K
    rho_solid: float = 8000.0
    cp_solid: float = 600.0

    @classmethod
    def sintered_powder(cls, d_particle, porosity, thickness, **kw):
        """Packed-sphere correlations: Carman-Kozeny K, r_eff ~ 0.21 d_p."""
        K = d_particle ** 2 * porosity ** 3 / (150.0 * (1.0 - porosity) ** 2)
        return cls(thickness, porosity, 0.21 * d_particle, K, **kw)

    def k_eff(self, k_liq):
        """Chi's effective conductivity of a liquid-saturated sintered wick."""
        e, ks = self.porosity, self.k_solid
        return k_liq * ((2 * k_liq + ks - 2 * (1 - e) * (k_liq - ks)) /
                        (2 * k_liq + ks + (1 - e) * (k_liq - ks)))


@dataclass
class HeatPipe:
    # Defaults: illustrative ~1 kW-class Na / superalloy pipe (NOT a flight design)
    L_evap: float = 0.40
    L_adia: float = 0.30
    L_cond: float = 0.50
    r_vapor: float = 0.010
    wall_thickness: float = 0.001
    wick: Wick = field(default_factory=lambda: Wick.sintered_powder(100e-6, 0.60, 1.5e-3))
    k_wall: float = 22.0
    rho_wall: float = 8000.0
    cp_wall: float = 600.0
    fluid: Sodium = field(default_factory=Sodium)
    # Condenser boundary
    emissivity: float = 0.85
    T_env: float = 100.0          # effective radiative sink, K
    rad_area_ratio: float = 1.0   # radiating area / bare tube area (fins > 1)
    h_sink: float = 0.0           # W/m2/K to a coolant / converter HX (0 = radiator only)
    T_cool: float = 500.0         # K
    # Environment / physics knobs
    g_adverse: float = 0.0        # m/s^2 pulling liquid AWAY from evaporator (0 = microgravity)
    r_nucleation: float = 2.54e-7
    accommodation: float = 1.0

    # --- derived geometry
    @property
    def L(self): return self.L_evap + self.L_adia + self.L_cond
    @property
    def r_inner(self): return self.r_vapor + self.wick.thickness
    @property
    def r_outer(self): return self.r_inner + self.wall_thickness
    @property
    def A_vapor(self): return math.pi * self.r_vapor ** 2
    @property
    def A_wick(self): return math.pi * (self.r_inner ** 2 - self.r_vapor ** 2)
    @property
    def A_wall(self): return math.pi * (self.r_outer ** 2 - self.r_inner ** 2)
    @property
    def L_eff(self): return 0.5 * self.L_evap + self.L_adia + 0.5 * self.L_cond

    # --- operating limits (W), vectorised in T
    def limits(self, T, g_adverse=None):
        f, w = self.fluid, self.wick
        g = self.g_adverse if g_adverse is None else g_adverse
        T = np.asarray(T, dtype=float)
        sig, rl, hfg = f.sigma(T), f.rho_l(T), f.hfg(T)
        Pv, rv, mv, ml = f.Psat(T), f.rho_v(T), f.mu_v(T), f.mu_l(T)
        Av, Aw, Le = self.A_vapor, self.A_wick, self.L_eff

        dP_cap = 2.0 * sig / w.r_eff
        dP_grav = rl * g * self.L                      # zero in microgravity
        F_l = ml * Le / (w.permeability * Aw * rl * hfg)            # Pa/W
        F_v = 8.0 * mv * Le / (math.pi * self.r_vapor ** 4 * rv * hfg)
        Q_cap = np.maximum(dP_cap - dP_grav, 0.0) / (F_l + F_v)

        Q_sonic = 0.474 * Av * hfg * np.sqrt(rv * Pv)                 # Busse
        Q_visc = Av * self.r_vapor ** 2 * hfg * rv * Pv / (16.0 * mv * Le)
        Q_ent = Av * hfg * np.sqrt(sig * rv / (2.0 * w.r_eff))
        ke = w.k_eff(f.k_l(T))
        Q_boil = (2 * math.pi * self.L_evap * ke * T /
                  (hfg * rv * math.log(self.r_inner / self.r_vapor))
                  * np.maximum(2 * sig / self.r_nucleation - dP_cap, 0.0))
        return dict(capillary=Q_cap, sonic=Q_sonic, viscous=Q_visc,
                    entrainment=Q_ent, boiling=Q_boil)

    def transport_limit(self, T, p=10.0):
        """Smooth minimum of all limits at scalar T (W); keeps the ODE RHS smooth."""
        v = np.array([float(x) for x in self.limits(T).values()])
        if np.any(v <= 0.0):
            return 0.0
        m = v.min()
        return float(m * np.sum((v / m) ** (-p)) ** (-1.0 / p))


# ----------------------------------------------------------------------------
# Transient simulator
# ----------------------------------------------------------------------------
def _smooth_min2(a, b, p=10.0):
    if a <= 0.0 or b <= 0.0:
        return 0.0
    m = min(a, b)
    return m * ((a / m) ** (-p) + (b / m) ** (-p)) ** (-1.0 / p)


@dataclass
class Result:
    t: np.ndarray
    Tw: np.ndarray              # (N, nt)
    z: np.ndarray
    T_vapor: np.ndarray
    Q_in: np.ndarray
    Q_transport: np.ndarray
    Q_limit: np.ndarray
    limit_name: list
    utilization: np.ndarray     # Q_in / weakest limit  (>1 => limit exceeded)
    cap_margin: np.ndarray      # 1 - dP_required/dP_capillary_max
    terminated: bool
    message: str


class HeatPipeSimulator:
    def __init__(self, hp: HeatPipe, n_nodes: int = 48, T_fail: float = 1500.0):
        self.hp, self.f, self.N = hp, hp.fluid, n_nodes
        self.T_fail = T_fail
        self.dz = hp.L / n_nodes
        self.z = (np.arange(n_nodes) + 0.5) * self.dz
        self.is_e = self.z < hp.L_evap
        self.is_c = self.z > hp.L_evap + hp.L_adia
        self.is_a = ~(self.is_e | self.is_c)
        if min(self.is_e.sum(), self.is_a.sum(), self.is_c.sum()) < 1:
            raise ValueError("Increase n_nodes: every section needs >= 1 node.")
        self.n_e = int(self.is_e.sum())
        self.A_int = 2 * math.pi * hp.r_vapor * self.dz
        self.A_out = 2 * math.pi * hp.r_outer * self.dz
        self.R_wall = math.log(hp.r_outer / hp.r_inner) / (2 * math.pi * hp.k_wall * self.dz)
        self.ln_w = math.log(hp.r_inner / hp.r_vapor)
        self.power = lambda t: 0.0

    # ---- thermal mass per node
    def _capacity(self, Tw):
        hp, w, f = self.hp, self.hp.wick, self.f
        C_wall = hp.rho_wall * hp.cp_wall * hp.A_wall
        C_wick = (w.porosity * f.rho_l(Tw) * f.cp_l(Tw)
                  + (1 - w.porosity) * w.rho_solid * w.cp_solid) * hp.A_wick
        return (C_wall + C_wick) * self.dz

    # ---- two-phase closure: vapor temperature + phase-change rates
    def closure(self, Tw):
        hp, f = self.hp, self.f
        ke = hp.wick.k_eff(f.k_l(Tw))
        R_rad = self.ln_w / (2 * math.pi * ke * self.dz) + self.R_wall

        def parts(Tv):
            h = f.h_interface(Tv, hp.accommodation)
            G = 1.0 / (R_rad + 1.0 / (h * self.A_int))
            hfg = float(f.hfg(Tv))
            m = G * (Tw - Tv) / hfg
            pos = m > 0
            E = float(m[pos].sum())
            Cd = float(-m[~pos].sum())
            Qlim = hp.transport_limit(Tv)
            E_eff = _smooth_min2(E, Qlim / hfg) if E > 0 else 0.0
            return m, pos, E, Cd, E_eff, hfg, Qlim

        def F(Tv):
            _, _, _, Cd, E_eff, _, _ = parts(Tv)
            return E_eff - Cd

        lo = max(float(Tw.min()) - 1.0, 385.0)
        hi = min(float(Tw.max()) + 1.0, 2350.0)
        if F(lo) <= 0.0:
            Tv = lo
        elif F(hi) >= 0.0:
            Tv = hi
        else:
            Tv = brentq(F, lo, hi, xtol=1e-10, rtol=1e-14, maxiter=200)

        m, pos, E, Cd, E_eff, hfg, Qlim = parts(Tv)
        if E > 0:
            m = np.where(pos, m * (E_eff / E), m)
        return dict(m=m, Tv=Tv, hfg=hfg, Q_limit=Qlim, ke=ke)

    def _sink(self, Tw):
        hp = self.hp
        Q = np.zeros(self.N)
        T = Tw[self.is_c]
        Q[self.is_c] = (hp.emissivity * SIGMA_SB * hp.rad_area_ratio * self.A_out
                        * (T ** 4 - hp.T_env ** 4)
                        + hp.h_sink * self.A_out * (T - hp.T_cool))
        return Q

    def rhs(self, t, Tw):
        hp = self.hp
        cl = self.closure(Tw)
        Q_heat = np.zeros(self.N)
        Q_heat[self.is_e] = self.power(t) / self.n_e
        Q_pc = cl["m"] * cl["hfg"]
        kA = hp.k_wall * hp.A_wall + cl["ke"] * hp.A_wick
        kf = 0.5 * (kA[1:] + kA[:-1])
        flux = kf * (Tw[1:] - Tw[:-1]) / self.dz
        cond = np.zeros(self.N)
        cond[:-1] += flux
        cond[1:] -= flux
        return (Q_heat - Q_pc - self._sink(Tw) + cond) / self._capacity(Tw)

    # ---- pressure diagnostics at one instant
    def pressure_profiles(self, Tw):
        hp, f, w = self.hp, self.f, self.hp.wick
        cl = self.closure(Tw)
        m, Tv = cl["m"], cl["Tv"]
        F = np.cumsum(m)[:-1]                           # vapor flow at faces, kg/s (+z)
        Rv = 8 * float(f.mu_v(Tv)) / (math.pi * float(f.rho_v(Tv)) * hp.r_vapor ** 4)
        dPv = Rv * F * self.dz
        Pv = np.concatenate([[0.0], -np.cumsum(dPv)])
        iref = int(np.argmax(self.is_a))
        Pv = Pv - Pv[iref] + float(f.Psat(Tv))
        rl, ml = float(f.rho_l(Tv)), float(f.mu_l(Tv))
        dPl = ml * F * self.dz / (rl * w.permeability * hp.A_wick) + rl * hp.g_adverse * self.dz
        Pl = np.empty(self.N)
        Pl[-1] = Pv[-1]                                  # flat meniscus at condenser end
        Pl[:-1] = Pv[-1] - np.cumsum(dPl[::-1])[::-1]
        Pc = Pv - Pl
        Pc_max = 2 * float(f.sigma(Tv)) / w.r_eff
        return dict(Pv=Pv, Pl=Pl, Pc=Pc, Pc_max=Pc_max, Tv=Tv)

    def run(self, t_end, power, T_init=900.0, n_out=300, rtol=1e-6, atol=1e-3):
        self.power = power if callable(power) else (lambda t, q=power: q)
        y0 = np.full(self.N, float(T_init))

        def ev(t, y):
            return self.T_fail - y.max()
        ev.terminal, ev.direction = True, -1

        sol = solve_ivp(self.rhs, (0.0, t_end), y0, method="BDF", rtol=rtol, atol=atol,
                        t_eval=np.linspace(0.0, t_end, n_out), events=ev)
        nt = sol.t.size
        Tv, Qin, Qtr, Qlim, util, marg = (np.zeros(nt) for _ in range(6))
        names = []
        for k in range(nt):
            Tw = sol.y[:, k]
            cl = self.closure(Tw)
            lim = {n: float(v) for n, v in self.hp.limits(cl["Tv"]).items()}
            name = min(lim, key=lim.get)
            Tv[k] = cl["Tv"]
            Qin[k] = self.power(sol.t[k])
            Qtr[k] = float(cl["m"][cl["m"] > 0].sum() * cl["hfg"])
            Qlim[k] = lim[name]
            names.append(name)
            util[k] = Qin[k] / max(lim[name], 1e-9)
            pp = self.pressure_profiles(Tw)
            marg[k] = 1.0 - pp["Pc"][0] / max(pp["Pc_max"], 1e-9)
        stopped = bool(sol.status == 1)
        msg = (f"Wall temperature exceeded {self.T_fail:.0f} K at t = {sol.t[-1]:.0f} s "
               "(dryout / hot-spot failure criterion)" if stopped else sol.message)
        return Result(sol.t, sol.y, self.z, Tv, Qin, Qtr, Qlim, names, util, marg, stopped, msg)


# ----------------------------------------------------------------------------
# Reporting / plotting
# ----------------------------------------------------------------------------
def print_limits(hp: HeatPipe, T: float):
    print(f"\nOperating limits at T_vapor = {T:.0f} K  (g_adverse = {hp.g_adverse:.2f} m/s^2)")
    for k, v in hp.limits(T).items():
        print(f"  {k:<12s} {float(v):10.0f} W")


def plot_results(hp, sim, res, Q_nom, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(2, 3, figsize=(16, 9))
    T = np.linspace(550, 1500, 200)

    a = ax[0, 0]
    for k, v in hp.limits(T, g_adverse=0.0).items():
        a.semilogy(T, v, label=k)
    a.semilogy(T, hp.limits(T, g_adverse=G0)["capillary"], "k--", label="capillary, 1 g evap-up")
    a.semilogy(T, hp.limits(T, g_adverse=-G0)["capillary"], "k:", label="capillary, 1 g evap-down")
    a.axhline(Q_nom, color="r", lw=1)
    a.set_ylim(10, 2e5)
    a.set(xlabel="Vapor temperature [K]", ylabel="Power limit [W]", title="Operating limits (solid: 0 g)")
    a.legend(fontsize=7)
    a.grid(alpha=.3)

    a = ax[0, 1]
    idx = {"Evaporator": sim.is_e, "Adiabatic": sim.is_a, "Condenser": sim.is_c}
    for lbl, msk in idx.items():
        a.plot(res.t, res.Tw[msk].mean(axis=0), label=lbl)
    a.plot(res.t, res.T_vapor, "k--", label="Vapor")
    a.set(xlabel="Time [s]", ylabel="Temperature [K]", title="Temperatures")
    a.legend(fontsize=8)
    a.grid(alpha=.3)

    a = ax[0, 2]
    a.plot(res.t, res.Q_in, label="Heat input")
    a.plot(res.t, res.Q_transport, label="Transported by pipe")
    a.plot(res.t, res.Q_limit, "r--", label="Weakest limit")
    a.set_ylim(0, max(1.2 * Q_nom, 1.2 * res.Q_in.max()))
    a.set(xlabel="Time [s]", ylabel="Power [W]", title="Power vs limit")
    a.legend(fontsize=8)
    a.grid(alpha=.3)

    a = ax[1, 0]
    for frac in (0.0, 0.25, 0.5, 1.0):
        k = min(int(frac * (res.t.size - 1)), res.t.size - 1)
        a.plot(res.z, res.Tw[:, k], label=f"t = {res.t[k]:.0f} s")
    a.axvspan(0, hp.L_evap, color="r", alpha=.07)
    a.axvspan(hp.L_evap + hp.L_adia, hp.L, color="b", alpha=.07)
    a.set(xlabel="z [m]", ylabel="Wall temperature [K]", title="Axial profile (red: evap, blue: cond)")
    a.legend(fontsize=8)
    a.grid(alpha=.3)

    a = ax[1, 1]
    pp = sim.pressure_profiles(res.Tw[:, -1])
    a.plot(res.z, pp["Pc"], label="Capillary pressure required")
    a.axhline(pp["Pc_max"], color="r", ls="--", label="Max capillary pressure 2σ/r_eff")
    a.set(xlabel="z [m]", ylabel="Pressure [Pa]", title="Capillary pressure demand (final state)")
    a.legend(fontsize=8)
    a.grid(alpha=.3)

    a = ax[1, 2]
    a.plot(res.t, res.utilization, label="Q_in / weakest limit")
    a.plot(res.t, 1 - res.cap_margin, label="ΔP_required / ΔP_cap,max")
    a.axhline(1.0, color="r", ls="--")
    a.set_ylim(0, 1.6)
    a.set(xlabel="Time [s]", ylabel="Utilization [-]", title="Limit utilization (>1 = dryout)")
    a.legend(fontsize=8)
    a.grid(alpha=.3)

    gtxt = "microgravity" if abs(hp.g_adverse) < 1e-9 else f"g_adverse = {hp.g_adverse:.2f} m/s²"
    fig.suptitle(f"Sodium heat pipe two-phase simulation ({gtxt})")
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    print(f"Saved figure: {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--power", type=float, default=1500.0, help="steady evaporator power [W]")
    ap.add_argument("--ramp", type=float, default=200.0, help="power ramp time [s]")
    ap.add_argument("--t-end", type=float, default=2500.0)
    ap.add_argument("--t-init", type=float, default=900.0, help="initial temperature [K]")
    ap.add_argument("--g", type=float, default=0.0,
                    help="acceleration pulling liquid away from evaporator [m/s^2]; 0 = microgravity")
    ap.add_argument("--nodes", type=int, default=48)
    ap.add_argument("--out", default="heatpipe_results.png")
    ap.add_argument("--no-plot", action="store_true")
    ap.add_argument("--limits-only", action="store_true")
    args = ap.parse_args()

    hp = HeatPipe(g_adverse=args.g)
    print_limits(hp, 1000.0)
    if args.limits_only:
        return

    sim = HeatPipeSimulator(hp, n_nodes=args.nodes)
    ramp = lambda t: args.power * min(1.0, t / max(args.ramp, 1e-9))
    t0 = time.time()
    res = sim.run(args.t_end, ramp, T_init=args.t_init)
    print(f"\nSolved in {time.time() - t0:.1f} s wall-clock. Status: {res.message}")
    k = -1
    print(f"Final t = {res.t[k]:.0f} s | Q_in = {res.Q_in[k]:.0f} W | transported = {res.Q_transport[k]:.0f} W")
    print(f"  T_evap = {res.Tw[sim.is_e, k].mean():.0f} K, T_vapor = {res.T_vapor[k]:.0f} K, "
          f"T_cond = {res.Tw[sim.is_c, k].mean():.0f} K")
    print(f"  weakest limit: {res.limit_name[k]} = {res.Q_limit[k]:.0f} W "
          f"(utilization {res.utilization[k]:.2f}); capillary margin {res.cap_margin[k]:.2f}")
    if res.utilization[k] > 1.0:
        print("  *** Operating limit exceeded: expect evaporator dryout in this configuration ***")
    if not args.no_plot:
        plot_results(hp, sim, res, args.power, args.out)


if __name__ == "__main__":
    main()
