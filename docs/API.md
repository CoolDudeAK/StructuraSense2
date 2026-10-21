# API quick reference
All paths start with `/api`. JSON in/out. Errors look like `{"error":{"code":"...","message":"..."}}`.
Auth: `Authorization: Bearer <token>` from `POST /auth/login`. Browser-only helpers (EventSource, `<img>`, downloads) accept `?token=`.
Devices send data with `X-Device-Key: ssk_...` instead. Roles: viewer < engineer < admin.

| Method & path | Role | Purpose |
|---|---|---|
| POST `/auth/login` `{email,password}` · POST `/auth/register` · GET `/auth/me` | – | sign in / up (new = viewer) |
| GET `/structures` · GET `/structures/<id>` · PATCH (data_mode sim\|live\|all) · POST · DELETE | v/e | portfolio + detail with zones, devices, health |
| GET `/structures/<id>/health` · `/health/history?hours=` · POST `/health/recompute` | v/e | health index |
| GET `/structures/<id>/readings?device_id=&hours=` · `/report` (HTML) · `/report?format=csv` | v | sensor data, printable report |
| GET/POST `/devices` · PATCH/DELETE `/devices/<id>` · POST `/devices/<id>/rotate-key` | v/e | devices (key shown once) |
| POST `/ingest/readings` `{device_id,readings:[{value,ts_ms?}]}` | key/e | scalar sensor data (tagged live) |
| POST `/ingest/waveform` `{device_id,fs,samples[]}` | key/e | one vibration capture |
| POST `/ingest/serial-lines` `{structure_id,lines[]}` | key/e | raw Arduino lines (`184,126,171`, `S1:..,S2:..,S3:..`, `S\|dev\|val`, `W\|dev\|fs\|v,v,..`) |
| POST `/ingest/csv/preview` · `/ingest/csv` (multipart) · GET `/ingest/csv/history` | e | CSV import (tagged file) |
| GET `/waveforms` · `/waveforms/<id>` · POST `/waveforms/simulate` · `/waveforms/<id>/baseline` · `/signal/analyze` | v/e | Signal Lab |
| POST `/vision/analyze` (multipart image) · GET `/vision/analyses` `/vision/samples` `/vision/detectors` | e/v | crack detection |
| GET `/alerts?status=active` · POST `/alerts/<id>/ack \| resolve {note} \| dismiss` | v/e | alerts |
| GET/POST `/maintenance` · PATCH `/maintenance/<id> {status}` | v/e | tasks; proposals need approval |
| `/impact/<sid>/overview, live, settings, demo, record/start, record/finish, calibration, baseline/save, trials, analysis, export.csv` | v/e | Impact Lab (rig) |
| GET `/sim/state` · POST `/sim/control, scenario, inject, step` | v/e | simulator |
| GET `/models` · POST `/models/<id>/retrain` | v/a | AI models + honesty metadata |
| GET/PUT/DELETE `/cloud/config` · POST `/cloud/test, sync-now, push-all` · GET `/cloud/status` | a | Supabase mirror |
| GET `/stream?token=` | v | Server-Sent Events: tick, p2p, waveform, health, alert, alert_update |
| GET `/system/status, provenance, audit` · GET/PUT `/settings` · GET/POST/PATCH `/users` · POST `/business/imaas-quote` | – | misc |

Example (device → server):
```
curl -X POST http://127.0.0.1:5000/api/ingest/readings -H "X-Device-Key: ssk_..." -H "Content-Type: application/json" -d '{"device_id":"esp-strain-04","readings":[{"value":142.5}]}'
```


## Sensor channels
* `GET /api/structures/<id>/channels` - per-channel `state` (active / inactive / disabled), `score`, `weight`, `effective_weight_pct`, `contribution`, device counts, `why_inactive`.
* `PUT /api/structures/<id>/channels/<key>` (engineer) - body `{"enabled": false}` switches a channel out of the overall score. Keys: strain_fatigue, load, vibration, deflection, thermal, environment, internal, cracks.
* Device kinds now include `rf_coil` (value = resonant frequency in kHz, EXPERIMENTAL).

## Element Test Lab (`/api/lab`)
* `GET /lab/spec` - procedures, grades, channels, input fields, codes (drives the form).
* `POST /lab/tests` (engineer) - `{element_type, procedure, grade, params{}, mode: "sim"|"manual", defect 0-1, metrics{channel:{field:number}}, channels[], exposure, label}`. Returns per-channel results, verdict and element index.
* `GET /lab/tests?element=cube|beam|slab|column`, `GET /lab/tests/<id>`, `DELETE /lab/tests/<id>` (engineer).
* `GET /lab/cube-group?grade=M25` - IS 456 group-of-4 compliance.
* `POST /lab/crack-photo` (engineer, multipart `image` + `scale_px_per_mm`) - measures a real photo.
* `GET /lab/export.csv`.
