#!/usr/bin/env python3
"""Reproducible water-meter anomaly analysis for the test assignment.

Input files (semicolon-separated, UTF-8):
  data/pokazaniya.csv
  data/pribory.csv
  data/sobytiya.csv

Only differences between consecutive calendar days are treated as daily
consumption. The script uses only Python standard library and writes all
result tables into ./results.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Callable, Iterable

getcontext().prec = 28

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "results"
OUT.mkdir(exist_ok=True)


@dataclass(frozen=True)
class Thresholds:
    negative_min: Decimal = Decimal("0.001")          # 1 litre
    absolute_spike: Decimal = Decimal("1.5")          # m3/day
    relative_spike_factor: Decimal = Decimal("5")
    relative_spike_floor: Decimal = Decimal("0.5")    # m3/day
    baseline_cap: Decimal = Decimal("10")             # technical extremes excluded from baseline
    unrealistic: Decimal = Decimal("20")              # m3/day
    leak_daily_min: Decimal = Decimal("0.001")         # >1 litre/day
    leak_days: int = 90
    zero_days: int = 30
    step_window: int = 30
    step_factor: Decimal = Decimal("3")
    step_abs_change: Decimal = Decimal("0.1")
    step_min_level: Decimal = Decimal("0.02")
    magnet_baseline_days: int = 14
    magnet_min_history_days: int = 7
    magnet_drop_factor: Decimal = Decimal("0.5")


T = Thresholds()


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def median(values: list[Decimal]) -> Decimal:
    values = sorted(values)
    n = len(values)
    if n == 0:
        raise ValueError("median() requires non-empty values")
    if n % 2:
        return values[n // 2]
    return (values[n // 2 - 1] + values[n // 2]) / Decimal(2)


def fmt(x: Decimal | None, places: int = 6) -> str:
    if x is None:
        return ""
    q = Decimal(1).scaleb(-places)
    value = x.quantize(q)
    text = format(value, "f").rstrip("0").rstrip(".")
    return text if text not in {"", "-0"} else "0"


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def load_data():
    readings: dict[str, list[tuple[date, Decimal, int]]] = defaultdict(list)
    with (DATA / "pokazaniya.csv").open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            readings[row["anon_id"]].append(
                (parse_date(row["data"]), Decimal(row["pokazanie"]), int(row["paketov_za_sutki"]))
            )
    for aid in readings:
        readings[aid].sort(key=lambda x: x[0])

    devices: dict[str, dict[str, str]] = {}
    with (DATA / "pribory.csv").open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            devices[row["anon_id"]] = row

    events: dict[str, dict[date, set[str]]] = defaultdict(lambda: defaultdict(set))
    with (DATA / "sobytiya.csv").open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            events[row["anon_id"]][parse_date(row["data"])].add(row["sobytie"])

    return readings, devices, events


def build_daily(readings):
    daily: list[dict] = []
    skipped_gaps = 0
    for aid, rows in readings.items():
        for i in range(1, len(rows)):
            prev_date, prev_value, prev_packets = rows[i - 1]
            curr_date, curr_value, curr_packets = rows[i]
            if (curr_date - prev_date).days != 1:
                skipped_gaps += 1
                continue
            daily.append(
                {
                    "anon_id": aid,
                    "data": curr_date,
                    "prev_data": prev_date,
                    "prev_pokazanie": prev_value,
                    "pokazanie": curr_value,
                    "paketov_za_sutki": curr_packets,
                    "prev_paketov_za_sutki": prev_packets,
                    "rashod": curr_value - prev_value,
                }
            )
    return daily, skipped_gaps


def longest_streak(records: list[dict], condition: Callable[[dict], bool]):
    best_len = 0
    best_start = best_end = None
    curr_len = 0
    curr_start = None
    prev_date = None

    for row in sorted(records, key=lambda x: x["data"]):
        if condition(row):
            if prev_date is not None and (row["data"] - prev_date).days == 1:
                curr_len += 1
            else:
                curr_len = 1
                curr_start = row["data"]
            prev_date = row["data"]
            if curr_len > best_len:
                best_len, best_start, best_end = curr_len, curr_start, row["data"]
        else:
            curr_len = 0
            curr_start = None
            prev_date = None
    return best_len, best_start, best_end


def near_multiple_32768(value: Decimal, tolerance: Decimal = Decimal("1")) -> bool:
    if value == 0:
        return False
    unit = Decimal("327.68")
    nearest = int((abs(value) / unit).to_integral_value(rounding=ROUND_HALF_UP))
    return nearest >= 1 and abs(abs(value) - Decimal(nearest) * unit) <= tolerance


def main() -> None:
    readings, devices, events = load_data()
    daily, skipped_gaps = build_daily(readings)

    daily_by: dict[str, list[dict]] = defaultdict(list)
    daily_map: dict[str, dict[date, Decimal]] = defaultdict(dict)
    for row in daily:
        daily_by[row["anon_id"]].append(row)
        daily_map[row["anon_id"]][row["data"]] = row["rashod"]

    # 1) Negative consumption
    negative = [r for r in daily if r["rashod"] <= -T.negative_min]
    write_csv(
        OUT / "01_negative_consumption.csv",
        ["anon_id", "data", "prev_pokazanie", "pokazanie", "rashod"],
        ({
            "anon_id": r["anon_id"], "data": r["data"].isoformat(),
            "prev_pokazanie": fmt(r["prev_pokazanie"]), "pokazanie": fmt(r["pokazanie"]),
            "rashod": fmt(r["rashod"]),
        } for r in sorted(negative, key=lambda x: x["rashod"])),
    )

    # 2) Absolute + relative spikes
    absolute_spikes = [r for r in daily if r["rashod"] > T.absolute_spike]
    baselines: dict[str, Decimal] = {}
    for aid, rows in daily_by.items():
        vals = [r["rashod"] for r in rows if Decimal("0") < r["rashod"] <= T.baseline_cap]
        if len(vals) >= 20:
            baselines[aid] = median(vals)

    relative_spikes = []
    for r in daily:
        base = baselines.get(r["anon_id"])
        if base is not None and base > 0 and r["rashod"] > T.relative_spike_floor and r["rashod"] >= T.relative_spike_factor * base:
            x = dict(r)
            x["baseline_median"] = base
            x["multiple"] = r["rashod"] / base
            relative_spikes.append(x)

    write_csv(
        OUT / "02_absolute_spikes.csv", ["anon_id", "data", "rashod"],
        ({"anon_id": r["anon_id"], "data": r["data"].isoformat(), "rashod": fmt(r["rashod"])}
         for r in sorted(absolute_spikes, key=lambda x: x["rashod"], reverse=True)),
    )
    write_csv(
        OUT / "02_relative_spikes.csv", ["anon_id", "data", "rashod", "baseline_median", "multiple"],
        ({
            "anon_id": r["anon_id"], "data": r["data"].isoformat(), "rashod": fmt(r["rashod"]),
            "baseline_median": fmt(r["baseline_median"]), "multiple": fmt(r["multiple"]),
        } for r in sorted(relative_spikes, key=lambda x: x["multiple"], reverse=True)),
    )

    # 3) Physically unrealistic values
    unrealistic = [r for r in daily if r["rashod"] > T.unrealistic]
    write_csv(
        OUT / "03_unrealistic_consumption.csv",
        ["anon_id", "data", "rashod", "bs", "tip", "model"],
        ({
            "anon_id": r["anon_id"], "data": r["data"].isoformat(), "rashod": fmt(r["rashod"]),
            "bs": devices[r["anon_id"]]["bs"], "tip": devices[r["anon_id"]]["tip"], "model": devices[r["anon_id"]]["model"],
        } for r in sorted(unrealistic, key=lambda x: x["rashod"], reverse=True)),
    )

    # 4) Leak candidates: positive consumption >1 litre every day for >=90 consecutive days
    leak_candidates = []
    for aid, rows in daily_by.items():
        length, start, end = longest_streak(rows, lambda r: r["rashod"] > T.leak_daily_min)
        if length >= T.leak_days:
            vals = [r["rashod"] for r in rows if start <= r["data"] <= end and r["rashod"] > T.leak_daily_min]
            leak_candidates.append({
                "anon_id": aid, "days": length, "start_date": start.isoformat(), "end_date": end.isoformat(),
                "median_rashod": median(vals),
            })
    write_csv(
        OUT / "04_leak_candidates.csv",
        ["anon_id", "days", "start_date", "end_date", "median_rashod", "bs", "tip", "model"],
        ({
            **r, "median_rashod": fmt(r["median_rashod"]),
            "bs": devices[r["anon_id"]]["bs"], "tip": devices[r["anon_id"]]["tip"], "model": devices[r["anon_id"]]["model"],
        } for r in sorted(leak_candidates, key=lambda x: x["days"], reverse=True)),
    )

    # 5) Zero consumption with packets for >=30 consecutive days
    zero_candidates = []
    for aid, rows in daily_by.items():
        length, start, end = longest_streak(rows, lambda r: r["rashod"] == 0 and r["paketov_za_sutki"] > 0)
        if length >= T.zero_days:
            period_rows = [r for r in rows if start <= r["data"] <= end]
            avg_packets = Decimal(sum(r["paketov_za_sutki"] for r in period_rows)) / Decimal(len(period_rows))
            zero_candidates.append({
                "anon_id": aid, "days": length, "start_date": start.isoformat(), "end_date": end.isoformat(),
                "avg_packets_per_day": avg_packets,
            })
    write_csv(
        OUT / "05_zero_consumption_with_packets.csv",
        ["anon_id", "days", "start_date", "end_date", "avg_packets_per_day", "bs", "tip", "model"],
        ({
            **r, "avg_packets_per_day": fmt(r["avg_packets_per_day"]),
            "bs": devices[r["anon_id"]]["bs"], "tip": devices[r["anon_id"]]["tip"], "model": devices[r["anon_id"]]["model"],
        } for r in sorted(zero_candidates, key=lambda x: x["days"], reverse=True)),
    )

    # 6) Step change: complete 30 calendar days before + 30 after, stable new level
    step_candidates = []
    w = T.step_window
    for aid, rows in daily_by.items():
        # Build runs of consecutive calendar days with technically valid consumption.
        runs = []
        run = []
        prev_day = None
        for r in sorted(rows, key=lambda x: x["data"]):
            valid = Decimal("0") <= r["rashod"] <= T.baseline_cap
            consecutive = prev_day is not None and (r["data"] - prev_day).days == 1
            if valid:
                if run and not consecutive:
                    runs.append(run)
                    run = []
                run.append(r)
                prev_day = r["data"]
            else:
                if run:
                    runs.append(run)
                    run = []
                prev_day = None
        if run:
            runs.append(run)

        best = None
        for run in runs:
            if len(run) < 2 * w:
                continue
            vals = [r["rashod"] for r in run]
            for i in range(w, len(run) - w + 1):
                med_before = median(vals[i-w:i])
                med_after = median(vals[i:i+w])
                if med_before < T.step_min_level or med_after < T.step_min_level:
                    continue
                ratio = max(med_before, med_after) / min(med_before, med_after)
                abs_change = abs(med_after - med_before)
                if ratio >= T.step_factor and abs_change >= T.step_abs_change:
                    candidate = {
                        "anon_id": aid, "split_date": run[i]["data"], "median_before": med_before,
                        "median_after": med_after, "ratio": ratio, "abs_change": abs_change,
                        "direction": "up" if med_after > med_before else "down",
                    }
                    if best is None or (ratio, abs_change) > (best["ratio"], best["abs_change"]):
                        best = candidate
        if best:
            step_candidates.append(best)

    write_csv(
        OUT / "06_step_changes.csv",
        ["anon_id", "split_date", "median_before", "median_after", "ratio", "abs_change", "direction", "bs", "tip", "model"],
        ({
            "anon_id": r["anon_id"], "split_date": r["split_date"].isoformat(),
            "median_before": fmt(r["median_before"]), "median_after": fmt(r["median_after"]),
            "ratio": fmt(r["ratio"]), "abs_change": fmt(r["abs_change"]), "direction": r["direction"],
            "bs": devices[r["anon_id"]]["bs"], "tip": devices[r["anon_id"]]["tip"], "model": devices[r["anon_id"]]["model"],
        } for r in sorted(step_candidates, key=lambda x: x["ratio"], reverse=True)),
    )

    # 7) Magnet association; duplicate event rows are collapsed to anon_id + date + event
    magnet_days = {(aid, event_date) for aid, by_date in events.items() for event_date, names in by_date.items() if "магнит" in names}
    magnet_rows, nonmagnet_rows = [], []
    for aid, m in daily_map.items():
        for day, current in m.items():
            hist = []
            for k in range(1, T.magnet_baseline_days + 1):
                hist_day = day - timedelta(days=k)
                if hist_day in m and Decimal("0") <= m[hist_day] <= T.baseline_cap:
                    hist.append(m[hist_day])
            if len(hist) < T.magnet_min_history_days:
                continue
            base = median(hist)
            if base < T.step_min_level or not (Decimal("0") <= current <= T.baseline_cap):
                continue
            row = {
                "anon_id": aid, "data": day, "rashod": current, "baseline_14d_median": base,
                "drop_50pct": current <= base * T.magnet_drop_factor,
            }
            (magnet_rows if (aid, day) in magnet_days else nonmagnet_rows).append(row)

    write_csv(
        OUT / "07_magnet_days.csv", ["anon_id", "data", "rashod", "baseline_14d_median", "drop_50pct"],
        ({
            "anon_id": r["anon_id"], "data": r["data"].isoformat(), "rashod": fmt(r["rashod"]),
            "baseline_14d_median": fmt(r["baseline_14d_median"]), "drop_50pct": int(r["drop_50pct"]),
        } for r in magnet_rows),
    )

    local_magnet = []
    for aid, m in daily_map.items():
        mag_vals, non_vals = [], []
        for day, value in m.items():
            if not (Decimal("0") <= value <= T.baseline_cap):
                continue
            (mag_vals if (aid, day) in magnet_days else non_vals).append(value)
        if len(mag_vals) >= 3 and len(non_vals) >= 20:
            med_mag, med_non = median(mag_vals), median(non_vals)
            if med_non >= T.step_min_level and med_mag <= med_non * Decimal("0.5"):
                local_magnet.append({
                    "anon_id": aid, "magnet_days": len(mag_vals), "median_magnet": med_mag,
                    "median_other": med_non, "ratio": med_mag / med_non,
                })
    write_csv(
        OUT / "07_local_magnet_candidates.csv",
        ["anon_id", "magnet_days", "median_magnet", "median_other", "ratio", "bs", "tip", "model"],
        ({
            "anon_id": r["anon_id"], "magnet_days": r["magnet_days"], "median_magnet": fmt(r["median_magnet"]),
            "median_other": fmt(r["median_other"]), "ratio": fmt(r["ratio"]),
            "bs": devices[r["anon_id"]]["bs"], "tip": devices[r["anon_id"]]["tip"], "model": devices[r["anon_id"]]["model"],
        } for r in sorted(local_magnet, key=lambda x: x["ratio"])),
    )

    # 8) Own findings
    pos_gt_100 = [r for r in daily if r["rashod"] > Decimal("100")]
    near_327_pos = sum(near_multiple_32768(r["rashod"]) for r in pos_gt_100)
    near_327_neg = sum(near_multiple_32768(r["rashod"]) for r in negative)

    unreal_ids = {r["anon_id"] for r in unrealistic}
    tip_unreal = Counter(devices[aid]["tip"] for aid in unreal_ids)
    bs_unreal = Counter(devices[aid]["bs"] for aid in unreal_ids)

    chronic_high = []
    for aid, rows in daily_by.items():
        vals = [r["rashod"] for r in rows if Decimal("0") <= r["rashod"] <= T.unrealistic]
        if len(vals) >= 60:
            med = median(vals)
            if med > Decimal("2"):
                chronic_high.append({"anon_id": aid, "valid_days": len(vals), "median_rashod": med})
    write_csv(
        OUT / "08_chronic_high_consumption.csv",
        ["anon_id", "valid_days", "median_rashod", "bs", "tip", "model"],
        ({
            **r, "median_rashod": fmt(r["median_rashod"]),
            "bs": devices[r["anon_id"]]["bs"], "tip": devices[r["anon_id"]]["tip"], "model": devices[r["anon_id"]]["model"],
        } for r in sorted(chronic_high, key=lambda x: x["median_rashod"], reverse=True)),
    )

    # Summary + consolidated device-level table for Power BI
    negative_ids = {r["anon_id"] for r in negative}
    absolute_ids = {r["anon_id"] for r in absolute_spikes}
    relative_ids = {r["anon_id"] for r in relative_spikes}
    leak_ids = {r["anon_id"] for r in leak_candidates}
    zero_ids = {r["anon_id"] for r in zero_candidates}
    step_ids = {r["anon_id"] for r in step_candidates}
    local_magnet_ids = {r["anon_id"] for r in local_magnet}
    chronic_ids = {r["anon_id"] for r in chronic_high}
    any_ids = negative_ids | absolute_ids | relative_ids | unreal_ids | leak_ids | zero_ids | step_ids

    anomaly_summary = [
        {"anomaly": "Negative consumption", "criterion": "<= -0.001 m3/day", "devices": len(negative_ids), "events": len(negative)},
        {"anomaly": "Absolute spike", "criterion": "> 1.5 m3/day", "devices": len(absolute_ids), "events": len(absolute_spikes)},
        {"anomaly": "Relative spike", "criterion": ">= 5x usual and > 0.5 m3/day", "devices": len(relative_ids), "events": len(relative_spikes)},
        {"anomaly": "Physically unrealistic", "criterion": "> 20 m3/day", "devices": len(unreal_ids), "events": len(unrealistic)},
        {"anomaly": "Leak candidate", "criterion": "> 0.001 m3/day for >= 90 consecutive days", "devices": len(leak_ids), "events": ""},
        {"anomaly": "Zero consumption with packets", "criterion": "0 m3/day for >= 30 consecutive days", "devices": len(zero_ids), "events": ""},
        {"anomaly": "Step change", "criterion": "30d before/after; >=3x and >=0.1 m3/day", "devices": len(step_ids), "events": ""},
    ]
    write_csv(OUT / "anomaly_summary.csv", ["anomaly", "criterion", "devices", "events"], anomaly_summary)

    summary_rows = [
        {"metric": "devices_total", "value": len(readings)},
        {"metric": "reading_rows", "value": sum(len(x) for x in readings.values())},
        {"metric": "adjacent_daily_pairs", "value": len(daily)},
        {"metric": "pairs_skipped_due_to_date_gap", "value": skipped_gaps},
        {"metric": "devices_with_any_main_anomaly", "value": len(any_ids)},
        {"metric": "negative_devices", "value": len(negative_ids)},
        {"metric": "negative_days", "value": len(negative)},
        {"metric": "absolute_spike_devices", "value": len(absolute_ids)},
        {"metric": "absolute_spike_days", "value": len(absolute_spikes)},
        {"metric": "relative_spike_devices", "value": len(relative_ids)},
        {"metric": "relative_spike_days", "value": len(relative_spikes)},
        {"metric": "unrealistic_devices", "value": len(unreal_ids)},
        {"metric": "unrealistic_days", "value": len(unrealistic)},
        {"metric": "leak_candidate_devices", "value": len(leak_ids)},
        {"metric": "zero_consumption_devices", "value": len(zero_ids)},
        {"metric": "step_change_devices", "value": len(step_ids)},
        {"metric": "magnet_eligible_days", "value": len(magnet_rows)},
        {"metric": "magnet_drop_50pct_days", "value": sum(r["drop_50pct"] for r in magnet_rows)},
        {"metric": "nonmagnet_eligible_days", "value": len(nonmagnet_rows)},
        {"metric": "nonmagnet_drop_50pct_days", "value": sum(r["drop_50pct"] for r in nonmagnet_rows)},
        {"metric": "local_magnet_candidate_devices", "value": len(local_magnet_ids)},
        {"metric": "positive_gt100_near_327_68", "value": near_327_pos},
        {"metric": "positive_gt100_total", "value": len(pos_gt_100)},
        {"metric": "negative_near_327_68", "value": near_327_neg},
        {"metric": "unrealistic_type_AQUA2", "value": tip_unreal.get("AQUA2", 0)},
        {"metric": "unrealistic_bs_07_05_03", "value": bs_unreal.get("BS-07", 0) + bs_unreal.get("BS-05", 0) + bs_unreal.get("BS-03", 0)},
        {"metric": "chronic_high_devices", "value": len(chronic_ids)},
    ]
    write_csv(OUT / "summary.csv", ["metric", "value"], summary_rows)

    neg_count = Counter(r["anon_id"] for r in negative)
    abs_count = Counter(r["anon_id"] for r in absolute_spikes)
    rel_count = Counter(r["anon_id"] for r in relative_spikes)
    unreal_count = Counter(r["anon_id"] for r in unrealistic)
    leak_by_id = {r["anon_id"]: r for r in leak_candidates}
    zero_by_id = {r["anon_id"]: r for r in zero_candidates}
    step_by_id = {r["anon_id"]: r for r in step_candidates}
    local_mag_by_id = {r["anon_id"]: r for r in local_magnet}
    chronic_by_id = {r["anon_id"]: r for r in chronic_high}

    device_rows = []
    for aid in sorted(devices):
        device_rows.append({
            "anon_id": aid, "bs": devices[aid]["bs"], "tip": devices[aid]["tip"], "model": devices[aid]["model"],
            "negative_flag": int(aid in negative_ids), "negative_days": neg_count[aid],
            "absolute_spike_flag": int(aid in absolute_ids), "absolute_spike_days": abs_count[aid],
            "relative_spike_flag": int(aid in relative_ids), "relative_spike_days": rel_count[aid],
            "unrealistic_flag": int(aid in unreal_ids), "unrealistic_days": unreal_count[aid],
            "leak_flag": int(aid in leak_ids), "leak_max_days": leak_by_id.get(aid, {}).get("days", 0),
            "zero_flag": int(aid in zero_ids), "zero_max_days": zero_by_id.get(aid, {}).get("days", 0),
            "step_flag": int(aid in step_ids), "step_ratio": fmt(step_by_id[aid]["ratio"]) if aid in step_by_id else "",
            "local_magnet_flag": int(aid in local_magnet_ids),
            "chronic_high_flag": int(aid in chronic_ids),
        })
    write_csv(
        OUT / "device_anomaly_flags.csv",
        ["anon_id", "bs", "tip", "model", "negative_flag", "negative_days", "absolute_spike_flag", "absolute_spike_days",
         "relative_spike_flag", "relative_spike_days", "unrealistic_flag", "unrealistic_days", "leak_flag", "leak_max_days",
         "zero_flag", "zero_max_days", "step_flag", "step_ratio", "local_magnet_flag", "chronic_high_flag"],
        device_rows,
    )

    magnet_rate = Decimal(sum(r["drop_50pct"] for r in magnet_rows)) / Decimal(len(magnet_rows)) * 100
    nonmagnet_rate = Decimal(sum(r["drop_50pct"] for r in nonmagnet_rows)) / Decimal(len(nonmagnet_rows)) * 100

    print(f"Devices: {len(readings)}")
    print(f"Daily adjacent pairs: {len(daily)}; skipped gaps: {skipped_gaps}")
    print(f"1) Negative: {len(negative_ids)} devices / {len(negative)} days")
    print(f"2) Absolute spikes: {len(absolute_ids)} devices / {len(absolute_spikes)} days")
    print(f"   Relative spikes: {len(relative_ids)} devices / {len(relative_spikes)} days")
    print(f"3) Unrealistic: {len(unreal_ids)} devices / {len(unrealistic)} days")
    print(f"4) Leak candidates: {len(leak_ids)} devices")
    print(f"5) Zero with packets: {len(zero_ids)} devices")
    print(f"6) Step changes: {len(step_ids)} devices")
    print(f"7) Magnet: {len(magnet_rows)} eligible days; >=50% drop {magnet_rate:.2f}%")
    print(f"   Non-magnet control: >=50% drop {nonmagnet_rate:.2f}%")
    print(f"8) Local magnet candidates: {len(local_magnet_ids)} devices")
    print(f"   Chronic high consumption: {len(chronic_ids)} devices")


if __name__ == "__main__":
    main()