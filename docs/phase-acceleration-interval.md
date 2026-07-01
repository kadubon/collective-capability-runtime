# Phase Acceleration Interval

CARA acceleration reports keep the old `margin_delta` and add interval fields for confidence, stale baseline, transport, calibration, hazard, authority, censoring, and competing-stop charges. `certified_acceleration_interval_candidate` requires a positive lower margin interval and a valid confidence budget.

Proxy-only evidence cannot enter safe capital intervals. Missing or stale baselines suspend interval candidates. The report is a protocol-relative candidate, not real ASI proof.

Boundary markers for agents and CCR audits: proxy-only evidence is diagnostic evidence only. It can narrow what to inspect next, but it cannot by itself certify real-world acceleration, settlement, or safe capital admission.
