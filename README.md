# Cluster Lights (BLE) — Home Assistant integration

Turns a Bluetooth LED cluster string into an ordinary Home Assistant light: **on/off, brightness and
all seven effect modes**, spoken directly to the controller over HA's own Bluetooth stack.

These are the several‑hundred‑LED warm‑white wire bundles that turn up in discount shops every winter —
[this listing](https://www.kabelshop.nl/PerfectLED-Clusterverlichting-met-app-7-meter-Bluetooth-576-LEDs-Binnen-Buiten-AX8718700-i7551-t101352.html)
is the exact 7 m / 576 LED variant this was built against; the same hardware turns up under other
labels. Out of the box they are controlled from a phone: the vendor's
[Light App](https://play.google.com/store/apps/details?id=com.novolink.lightapp) over Bluetooth Low
Energy. That works, but it is a phone app — one light, in range, operated by hand. None of it touches a
cloud, so there is no good reason these cannot just be entities that join in with everything else you
automate.

Two things make that awkward without this integration:

- **The old package id is dead.** Documentation around these lights still points at
  `com.scinan.novolink.lightstring`, which now 404s on the Play Store (checked 2026‑08‑07). The app
  linked above is the one that resolves.
- **The existing integration no longer runs.** The original
  [BasVerkooijen/cluster-lights-home-assistant](https://github.com/BasVerkooijen/cluster-lights-home-assistant)
  is built on `bluepy`, which wants the Bluetooth adapter to itself; modern Home Assistant does not give
  it up. This is a ground‑up async rewrite — same device, same reverse‑engineered protocol, but it uses
  HA's Bluetooth stack instead of fighting it, and it **connects reliably**.

Related: [gruijter/com.gruijter.clusterlights](https://github.com/gruijter/com.gruijter.clusterlights)
covers the same BLE light family (Novolink, happylighting, Lumineo) for Homey rather than
Home Assistant.

## Status and scope

Small and deliberately narrow: about 120 lines doing one job. There is not much here to rot, so it
should be close to maintenance‑free — but it is maintained, and bugs get fixed.

- **Confirmed on:** control box labelled `AX8-…`, BLE name `LED-4-01-…`, GATT service `fff0`, warm‑white
  single‑channel string (brightness and patterns, no colour).
- **Pull requests welcome**, particularly for other controller variants.
- These strings are re‑sourced every season, so another production year may well speak different bytes.
  If yours does, the protocol table below plus [nRF Connect](https://www.nordicsemi.com/Products/Development-tools/nrf-connect-for-mobile)
  will get you the packets — a PR adding the variant is very welcome.
- If it will not connect at all, read "Two failure modes" below first; it separates the radio problem
  from the timing problem, which need completely different fixes.

## Features
- On / off
- Brightness (0–100 %)
- 7 effect modes: Wave, Phase, Phased Fade, Phased Twinkle, Fade, Fast Twinkle, Steady
- Uses HA's native Bluetooth — works with local USB/onboard adapters **and ESP32 Bluetooth proxies**
- No `bluepy`, no side threads, no external daemons; fully async on HA's event loop

## Supported hardware

**Confirmed on exactly one device**, and I want to be straight about that rather than imply a
compatibility list I cannot stand behind — I own one of these lights and cannot test anything else:

- Warm‑white cluster string, control box labelled `AX8-…`, PerfectLED‑branded packaging
- BLE advertised name `LED-4-01-…`
- GATT service `0000fff0‑…`, **write** characteristic `0000fff1‑…` (write‑without‑response), notify `fff4`

Other controllers in this family plausibly speak the same protocol, but *plausibly* is the honest word:
these strings are re‑sourced every season and different production years may use different bytes. If
yours advertises that GATT profile (check with [nRF Connect](https://www.nordicsemi.com/Products/Development-tools/nrf-connect-for-mobile)),
it is worth trying — and if it works, or if it needs different packets, please open a PR or an issue
saying so. That is the only way this list can ever grow honestly.

For **Lumineo** and **happylighting** strings specifically, see the Homey app linked under
[Credits](#credits-and-related-work) — it already handles those, and this integration does not.

## Installation

### HACS (custom repository)
1. HACS → ⋮ → **Custom repositories** → add `https://github.com/kai-wedekind/ha-clusterlights`, category **Integration**.
2. Install **Cluster Lights (BLE)**, then restart Home Assistant.

### Manual
Copy `custom_components/clusterlights/` into your HA `config/custom_components/` and restart.

## Configuration

**Settings → Devices & Services → Add Integration → Cluster Lights.**

Home Assistant may offer the light on its own once an adapter hears it advertising. If it does not,
add it manually: the dialog lists any matching controller already heard, and falls back to typing the
Bluetooth address. **An empty list normally means "not heard yet", not "not there"** — these strings
beacon only every 16–28 s, so give it a minute.

Setup deliberately does **not** test the connection. It usually happens indoors with the light outside
and possibly unpowered, where a probe would fail for reasons that say nothing about whether the address
is right.

Requirements:
- HA's **Bluetooth** integration set up, with an adapter (or **ESP32 Bluetooth proxy**) in range of the light.
- The light's BLE address, if it is not discovered — via Developer Tools → the Bluetooth "subscribe
  advertisements" action, nRF Connect, or the vendor app.

<details>
<summary>YAML (deprecated, still works)</summary>

Existing YAML configuration is **imported automatically** into a config entry on upgrade — nothing
breaks — and then logs a warning asking you to delete the block:

```yaml
light:
  - platform: clusterlights
    devices:
      "AA:BB:CC:DD:EE:FF":      # your light's BLE MAC (public / static)
        name: Cluster Light
```
</details>

## How it works (and why the old one didn't)
These controllers are **slow, weak BLE advertisers** — they beacon only every ~15–30 s. The original
integration (and a naïve `bleak` port) reused a *stale* device handle and gave up after a few seconds, so
connections constantly timed out. What makes this one reliable:

- HA‑native `bluetooth.async_ble_device_from_address(connectable=True)` + `bleak_retry_connector.establish_connection`
- `max_attempts=12` **and** a `ble_device_callback` that re‑fetches a **fresh** `BLEDevice` from HA on every
  retry — so it waits out the slow advertising and connects on the *next* beacon instead of failing on a stale one
- **connect → write → disconnect** per command — no persistent connection held, so the light's single BLE slot
  stays free for the phone app / other controllers between commands

## Two failure modes — tell them apart before you debug

They look identical from the dashboard and have completely different fixes. The error text tells you which
one you have:

**1. "not heard right now" — fails instantly (well under a second).**
No adapter has received an advertisement, so there is nothing to connect *to*. Retrying will not help;
this is a reception problem. It is worth knowing how weak the signal is to begin with: measured here at
**−71…−75 dBm at ~4 m around a corner, advertising only about once every 16–28 s**. With that little
margin, an indoor radio and an outdoor light can simply fail to meet — in one 15‑minute test here,
polling continuously, **not a single advertisement arrived**, while on other occasions the same light
was heard from indoors and controlled normally. I have not isolated which variable decides it (position,
an intervening door or window, the controller not advertising after power‑on), so treat this as
"sometimes it is not heard" rather than a rule.

Fix: put the radio on the light's side of whatever is in the way, with an **ESP32 ESPHome active
Bluetooth proxy** — HA and this integration use it transparently, no config change here.

**2. Heard, but the connection times out — fails slowly (seconds to a minute).**
The device is advertising and the adapter hears it, but `establish_connection` gives up. This is the one
the old integration never solved, and it is what `max_attempts=12` plus the `ble_device_callback` fixes
(see above). If you hit it anyway, check that no phone or PC is holding the light's single connection
slot, and note that the controller goes quiet after a burst of failed connects — power‑cycle it.

## Limitations
- State is **assumed** (`assumed_state`): the entity tracks the last command — it does not read the light back
  (these controllers are fire‑and‑forget). Commands always apply; the displayed state is a best guess. If the
  light is also on a smart plug, the plug is your reliable, always‑works on/off.

## Protocol reference
Write to characteristic `fff1` (write‑without‑response):

| Command | Bytes |
|---|---|
| On | `01 01 01 01` |
| Off | `01 01 01 00` |
| Brightness (0–99) | `03 01 01 <level>` |
| Mode | `05 01 02 03 <flag>` |

Mode flags: Wave `0x01`, Phase `0x02`, Phased Fade `0x04`, Phased Twinkle `0x08`, Fade `0x10`,
Fast Twinkle `0x20`, Steady `0x40`. No pairing / auth / encryption.

## Credits and related work

- **[BasVerkooijen/cluster-lights-home-assistant](https://github.com/BasVerkooijen/cluster-lights-home-assistant)** —
  originally reverse‑engineered this BLE protocol. Thank you: that work is why any of this is possible.
  This integration reuses the *protocol*; the code is an independent async rewrite and shares no source
  with it.
- **[gruijter/com.gruijter.clusterlights](https://github.com/gruijter/com.gruijter.clusterlights)** —
  honourable mention. A Homey app covering the same family of BLE string lights and, unlike this
  integration, **several brands**: Novolink, happylighting and Lumineo. **If your light is a
  Lumineo or happylighting and this integration does not speak to it, look there** — it may already
  know your bytes. No code from it is used here; it is GPL‑3.0 and this project is MIT, and the two
  do not mix in that direction.

## License
[MIT](LICENSE)
