# Synthetic dataset provenance

**These readings are synthetic. They do not represent any real laboratory or campus.**

- Generator: synthetic_generator_v1
- Seed: 42
- Local dates: 2026-07-06 to 2026-10-03 (90 days)
- Labs: 3 (see labs.csv)
- Readings written: 6469 hourly rows, stored in UTC. Missing hours are removed on purpose.
- readings.csv sha256: bcd4a82d0c936d2285819656c2032379c011460da90dfca2962b7d8c6b060db0

## Model assumptions
- Each computer draws idle_w when on but unused and active_w when in use.
- A base load covers lighting and HVAC while the lab is open. When closed, the base load drops to 10% and idle draw to 15%.
- Each hour has about 4% multiplicative noise.
- Holiday and exam dates are assumptions, not official academic calendar dates.
- Exam windows extend opening hours by 2 hours.
- No real tariff or emission factor is used anywhere in this dataset.
- equipment.csv lists computers at their active power. These are model assumptions, not measured ratings.

## Injected anomalies (anomalies.csv)
anomalies.csv is ground truth for evaluating alert rules later.
- `suspected_wastage` marks periods a rule should flag for human review. It is not confirmed wastage.
- `legitimate` and `data_quality` periods should not be reported as wastage.
