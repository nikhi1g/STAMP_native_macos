# Future work: runtime and latency

Not scheduled. Recorded 2026-10-21. The current release line (2.1.x) stays as is: feature
development is paused except for needed fixes.

## Goal (user's direction)
Improve runtime and latency (launch time, analysis and plot responsiveness, app size) while
preserving 1:1 functionality with STAMP 2.1.3: the same tests, effect sizes, corrections,
filters, plots, windows and results.

## Directions to evaluate
- **Rust** for the statistical core and data handling (the `metagenomics/` layer and plugin
  computations), called from the existing app or from a new front end.
- **A faster UI** than PyQt6 + matplotlib, keeping STAMP's layout and Windows look.
- **A custom computation kernel/engine** for the runtime (vectorised or compiled statistics,
  bootstrap/permutation loops, multiple-comparison corrections).

## Constraints that carry over
- 1:1 functionality is the acceptance criterion. The existing suites are the gate:
  `tests/test_golden_parity.py` (2,558 scenarios against the Python 2 build; numeric 1e-6,
  significance decisions exact) and `tests/accuracy/` (mpmath ground truth). The 13 pinned
  upstream defects stay identical unless the user decides otherwise.
- Distribution stays as built: Developer ID signing, notarization, the zip + move to
  Applications, Sparkle updates through the mimg.io feed, semantic versions.
- GPL-3.0 applies to any rewrite derived from STAMP.

## Measure first
Before choosing a stack, record baselines: cold and warm launch time, time to load a profile,
time per statistical test and per plot on the 109BL soil tables and the upstream examples,
memory, and app size. A rewrite is justified only where these show a user-visible gap.
