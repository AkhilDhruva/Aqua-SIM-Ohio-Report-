#!/usr/bin/env python3
"""Re-check every number quoted in CLAIMS_STATUS.md against its source file.

Usage: python3 analysis/verify_published_numbers.py     (from the repo root)

A study that reports numbers should be able to prove, mechanically, that the
numbers in its prose still match the files those numbers came from. Prose and
data drift apart silently — a table gets edited, a run gets rerun, a rounding
changes — and nothing complains. This complains.

Exit status is 0 only if every assertion holds, so it can be run in CI or before
tagging a version. It reads only committed artefacts; it never recomputes
physics, so it verifies REPORTING FIDELITY, not correctness of the science.
"""
import json
import sys

OK, BAD = [], []


def chk(label, got, want, tol=0.005):
    good = abs(got - want) <= tol if isinstance(want, (int, float)) and \
        isinstance(got, (int, float)) else got == want
    (OK if good else BAD).append(f"{label}: claimed {want!r}, file says {got!r}")


def main():
    ca_p = json.load(open('analysis/corridor_analysis_pataskala_c.json'))[0]
    ca_f = json.load(open('analysis/corridor_analysis_franklinton_c.json'))[0]
    P = {r['probe']: r for r in ca_p['probes']}
    F = {r['probe']: r for r in ca_f['probes']}

    # --- C8: Pataskala corridor table ------------------------------------
    chk('main_broad road peak', P['main_broad_pataskala']['road_peak_m'], 3.69, 0.006)
    chk('main_broad channel peak', P['main_broad_pataskala']['channel_peak_m'], 4.47, 0.006)
    chk('kirkersville road peak', P['kirkersville_gauge_03144816']['road_peak_m'], 2.99, 0.006)
    chk('sr310 road peak', P['sr310_sf_crossing']['road_peak_m'], 0.20, 0.006)
    chk('sr310 channel peak', P['sr310_sf_crossing']['channel_peak_m'], 4.28, 0.006)
    chk('sr310 road-minus-channel differential',
        round(P['sr310_sf_crossing']['channel_peak_m']
              - P['sr310_sf_crossing']['road_peak_m'], 2), 4.07)

    # --- C10a: US-40 stayed under the impassable threshold ----------------
    chk('us40_etna road peak', P['us40_etna']['road_peak_m'], 0.04, 0.006)
    chk('us40_east road peak', P['us40_east']['road_peak_m'], 0.22, 0.006)
    chk('us40_east never impassable', P['us40_east']['road_impassable_utc'], None)
    chk('us40_etna never impassable', P['us40_etna']['road_impassable_utc'], None)
    chk('main_broad impassable at', P['main_broad_pataskala']['road_impassable_utc'], '08-20 06:12Z')
    chk('main_broad caution at', P['main_broad_pataskala']['road_caution_utc'], '08-20 05:58Z')
    chk('us40_east caution at', P['us40_east']['road_caution_utc'], '08-20 08:42Z')

    # --- C8b: Franklinton bounds the diagnostic ---------------------------
    chk('wbroad_hilltop road peak', F['wbroad_hilltop']['road_peak_m'], 2.22, 0.006)
    chk('franklinton_core road peak', F['franklinton_core']['road_peak_m'], 1.70, 0.006)
    chk('olentangy road peak', F['olentangy_gauge_03227107']['road_peak_m'], 2.17, 0.006)

    # both nests must be FINAL, not partial (the EF-2 rule)
    chk('pataskala complete', ca_p['complete'], True)
    chk('franklinton complete', ca_f['complete'], True)

    # --- C8a / C8c: gauge timing -----------------------------------------
    g_f = json.load(open('analysis/gauge_timing_corridor_franklinton_c_B.json'))['gauges'][0]
    g_p = json.load(open('analysis/gauge_timing_corridor_pataskala_c_B.json'))['gauges'][0]
    chk('franklinton peak error +31 min', g_f['peak_time_error_min'], 31, 0.5)
    chk('franklinton shape r', g_f['shape_corr'], 0.917, 0.0005)
    chk('pataskala peak error -153 min', g_p['peak_time_error_min'], -153, 0.5)
    chk('pataskala shape r', g_p['shape_corr'], 0.854, 0.0005)

    # --- consolidated scoring --------------------------------------------
    ct = json.load(open('analysis/consolidated_table.json'))
    chk('scoreable rows', ct['scoreable_rows'], 5)
    chk('confirmed', ct['confirmed'], 4)
    chk('failed', ct['failed'], 1)
    chk('unscoreable', ct['unscoreable_rows'], 7)

    # --- C8d: the Froude episode was transient ----------------------------
    ff = [json.loads(l) for l in open('analysis/fast_face_log.jsonl') if l.strip()]
    fr = [d for d in ff if 'frank' in d['run']]
    chk('froude first sample', fr[0]['interior_median_froude_of_fast'], 3.53, 0.005)
    chk('froude last sample', fr[-1]['interior_median_froude_of_fast'], 1.68, 0.005)
    chk('volume first (10^6 m3)', round(fr[0]['volume_m3'] / 1e6, 2), 1.97, 0.005)
    chk('volume last (10^6 m3)', round(fr[-1]['volume_m3'] / 1e6, 2), 4.83, 0.005)
    chk('ghost outfall first', fr[0]['ghost_outfall_max_v_ms'], 169.02, 0.02)
    chk('ghost outfall last', fr[-1]['ghost_outfall_max_v_ms'], 56.71, 0.02)
    # the claim "no cell is ever negative or non-finite" must hold on EVERY sample
    chk('negative or non-finite cells, all samples',
        sum(d['negative_depths'] + d['nonfinite'] for d in ff), 0)
    # Froude must FALL overall, and any reversal must stay small — the claim is
    # "declines with one 0.02 reversal", not "monotonic". This assertion is what
    # caught the original wording, which overstated it as monotonic.
    seq = [d['interior_median_froude_of_fast'] for d in fr]
    rises = [round(b - a, 4) for a, b in zip(seq, seq[1:]) if b > a]
    chk('froude declines overall', seq[-1] < seq[0], True)
    chk('froude reversals count', len(rises), 1)
    chk('largest froude reversal', max(rises) if rises else 0.0, 0.02, 0.0005)
    # volume, unlike Froude, genuinely is monotonic
    vol = [d['volume_m3'] for d in fr]
    chk('volume monotonically non-decreasing',
        all(b >= a for a, b in zip(vol, vol[1:])), True)

    # --- C8b provenance: the wbroad_hilltop peak is a single-sample overshoot
    # on a genuine wetting front. Assert both halves, so neither the quoted peak
    # nor the "not a false alarm" defence can drift without this failing.
    import numpy as _np
    ser = json.load(open('runs/franklinton_c_B/probe_series.json'))
    tt = _np.asarray(ser['t_s'], float) / 3600.0
    wb = _np.asarray(ser['groups']['wbroad_hilltop']['depth_max_m'], float)
    kmax = int(_np.argmax(wb))
    chk('wbroad quoted peak', round(float(wb[kmax]), 3), 2.219, 0.0006)
    chk('wbroad sustained peak excluding the overshoot',
        round(float(_np.delete(wb, kmax).max()), 4), 2.2082, 0.0006)
    chk('wbroad overshoot is exactly one sample',
        sum(1 for i in range(1, len(wb) - 1)
            if wb[i] > wb[i - 1] + 0.5 and wb[i] > wb[i + 1] + 0.5), 1)
    chk('wbroad never drops below 0.30 m after the front',
        bool((wb[kmax:] >= 0.30).all()), True)
    chk('wbroad minimum in the hour after the front',
        round(float(wb[kmax + 1:kmax + 61].min()), 3), 0.797, 0.0006)
    # no OTHER probe series may contain a spike
    spiky = []
    for run in ('pataskala_c_B', 'franklinton_c_B'):
        dd = json.load(open(f'runs/{run}/probe_series.json'))
        for g, v in dd['groups'].items():
            a = _np.asarray(v['depth_max_m'], float)
            if any(a[i] > a[i - 1] + 0.5 and a[i] > a[i + 1] + 0.5
                   for i in range(1, len(a) - 1)):
                spiky.append(g)
    chk('probe series containing a single-sample spike', sorted(spiky), ['wbroad_hilltop'])

    # --- run metadata -----------------------------------------------------
    chk('franklinton peak depth', json.load(open('runs/franklinton_c_B/meta.json'))['peak_depth_m'],
        9.818, 0.0005)
    chk('pataskala peak depth', json.load(open('runs/pataskala_c_B/meta.json'))['peak_depth_m'],
        5.104, 0.0005)

    total = len(OK) + len(BAD)
    print(f"verified {len(OK)}/{total} published numbers against their source files")
    for b in BAD:
        print("  MISMATCH:", b)
    return 1 if BAD else 0


if __name__ == '__main__':
    sys.exit(main())
