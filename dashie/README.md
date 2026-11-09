# Running this on wall tablets (Dashie) — optional

This is **added value, not a requirement.** The core kit (`packages/` +
`lovelace/`) works on any Home Assistant dashboard. This folder is one extra
tile for anyone who, like the original author, runs
[Dashie](https://github.com/jcwillox/dashie) as a kiosk dashboard on cheap
Android tablets mounted by the door.

`boiler-tile-ring-gauge.yaml` is a bigger, ring-gauge version of the status
card — same data as `lovelace/boiler-card-button-card.yaml`, styled for a
tablet people glance at while walking past rather than a phone screen people
tap into.

Drop it into any Dashie view's `cards:` list (or any button-card-capable
Lovelace dashboard, Dashie isn't actually required to use this one file —
only the HACS button-card dependency is). Needs the same button-card
integration as the HACS Lovelace card.
