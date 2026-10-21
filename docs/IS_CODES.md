# IS-code register (Element Test Lab)

**Status: INDICATIVE. Every value below is the team's reading from secondary summaries. None was checked against the purchased BIS text. Verify before relying on it. Never use lab-bench output as a test certificate.**

| Check | Rule used | Source |
|---|---|---|
| Cube acceptance (group of 4) | mean >= max(fck + 0.825 sigma, fck + 4) [fck+3 for M15]; each result >= fck - 4 [fck-3 for M15]. Assumed sigma: 3.5 (<=M15), 4.0 (M20-M25), 5.0 (M30-M50), 6.0 (M55+) | IS 456:2000 cl.16, Table 11, Table 8 |
| Single cube | shown against fck (not an acceptance test) | IS 456 / IS 516 |
| Cube test conditions | load 14 N/mm2 per min, curing 27 +/- 2 C | IS 516 |
| Modulus of elasticity | Ec = 5000 sqrt(fck) MPa; measured >= 0.85x flagged OK | IS 456 cl.6.2.3.1 |
| Flexural strength | fcr = 0.7 sqrt(fck); measured fcr = P l / (b d2), crack in middle third | IS 456 cl.6.2.2, IS 516 |
| Ultrasonic pulse velocity | >4.5 excellent, 3.5-4.5 good, 3.0-3.5 medium, <3.0 doubtful | IS 13311 (Part 1) |
| Member load test | 24 h under load; deflection < 40 l2/D (l in m, D in mm) means recovery not required; else recovery >= 75 % within 24 h; (repeat after 72 h, second recovery about 80 %) | IS 456 cl.17.6 (one secondary source quotes a different constant: verify) |
| Deflection limit | span/250 | IS 456 cl.23.2 |
| Crack width | 0.3 mm general, 0.2 mm weather/moisture exposure, 0.1 mm severe | IS 456 cl.35.3.2 |
| Column | e_min = max(l/500 + D/30, 20 mm); short if le/D < 12; Pu = 0.4 fck Ac + 0.67 fy Asc | IS 456 cl.25.4, 25.1.2, 39.3 |
| Frequency drop, temperature range, moisture limit | project thresholds, **no IS code** | StructuraSense |
| RF-coil resonance shift | **no standard**, experimental, INFO / indicative only | StructuraSense |

Simulated readings are produced by simple formulas (see `backend/services/elements.py`, function `simulate`) plus noise, and are always labelled SIMULATED.
