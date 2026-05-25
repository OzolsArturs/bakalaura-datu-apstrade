#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""

No ievades faila tiek iegūtas 4 aktivitātes:
1) ierasanās krustojumā;
2) gaidīšana pie luksofora;
3) krustojuma škērsošana;
4) izbraukšana no krustojuma.

"""
import re, csv
from datetime import datetime, timedelta
from collections import Counter

IEEJAS_FAILS = r"C:\Users\direk\Downloads\Krustojums_15032026 (1).out.txt"
IZEJAS_FAILS = r"C:\Users\direk\Desktop\Bakalaura darbam\krustojums_event_log.csv"
BAZES_DATUMS = datetime(2026, 3, 15, 0, 0, 0)

RE_LAIKS   = re.compile(r"^Time:\s+([0-9.]+)\s+Entity:\s+(\d+)")
RE_BLOKS   = re.compile(r"^\s*\d+\s+\S+\s+([A-Z]+)\s*$")
RE_TIPS    = re.compile(r"Entity Type set to (\w+)")
RE_STACIJA = re.compile(r"entered station (R\d)P")
RE_SEIZE   = re.compile(r"Seized [0-9.]+ unit\(s\) of resource Enter_(\d)")
RE_RELEASE = re.compile(r"Enter_(\d) available increased")
RE_WAIT    = re.compile(r"QR(\d)\.WaitingTime recorded ([0-9.]+)")

def parse_trase(cels):
    e = {}
    def ieraksts(eid):
        if eid not in e:
            e[eid] = {"tips": None, "marsruts": None, "t_create": None,
                      "t_queue": None, "t_release": None, "t_dispose": None, "t_seize": None,
                      "gaidisana": None, "t_first": None, "t_station": None}
        return e[eid]
    laiks, aktiv = 0.0, None
    with open(cels, "r", encoding="utf-8", errors="replace") as f:
        for rinda in f:
            rinda = rinda.rstrip("\r\n")
            m = RE_LAIKS.match(rinda)
            if m:
                laiks = float(m.group(1)); aktiv = int(m.group(2))
                r = ieraksts(aktiv)
                if r["t_first"] is None: r["t_first"] = laiks
                continue
            if aktiv is None: continue
            r = ieraksts(aktiv)
            mb = RE_BLOKS.match(rinda)
            if mb:
                b = mb.group(1)
                if b == "CREATE" and r["t_create"] is None: r["t_create"] = laiks
                elif b == "QUEUE" and r["t_queue"] is None: r["t_queue"] = laiks
                elif b == "SEIZE" and r.get("t_seize") is None: r["t_seize"] = laiks
                elif b == "DISPOSE": r["t_dispose"] = laiks
                continue
            mt = RE_TIPS.search(rinda)
            if mt: r["tips"] = mt.group(1)
            ms = RE_STACIJA.search(rinda)
            if ms:
                if r["marsruts"] is None: r["marsruts"] = ms.group(1)
                if r["t_station"] is None: r["t_station"] = laiks   # patiesa ierasanas = pirma stacija
            mw = RE_WAIT.search(rinda)
            if mw and r["gaidisana"] is None:
                r["marsruts"] = "R" + mw.group(1); r["gaidisana"] = float(mw.group(2))
            msz = RE_SEIZE.search(rinda)
            if msz: r["marsruts"] = "R" + msz.group(1)
            mr = RE_RELEASE.search(rinda)
            if mr:
                r["marsruts"] = "R" + mr.group(1)
                if r["t_release"] is None: r["t_release"] = laiks
    return e

def veido_event_log(entiti):
    rindas, izlaisti = [], 0
    for eid, r in entiti.items():
        # Apstrādē tiek izmantoti tikai tās entitijas, kam ir gan rindas, gan škērsošanas notikums.
        if r["t_queue"] is None or r["t_seize"] is None:
            izlaisti += 1
            continue
        # Ierašanās brīdis tiek noteikts pēc pirmās maršruta stacijas.
        # Tas ļauj korekti apstrādāt arī autobusus, kuri sākumā tiek izveidoti kā plānošanas entītiji.
        t_ier = r["t_station"] if r["t_station"] is not None else (
                r["t_create"] if r["t_create"] is not None else r["t_first"])
        t_que = r["t_queue"]
        t_sker = r["t_seize"]                      # SEIZE bloks = sak skersot (sanem zalo signalu)
        if t_sker < t_que: t_sker = t_que
        gaid_min = max(0.0, t_sker - t_que)        # gaidisanas laiku apreikina = SEIZE - QUEUE
        t_izb = r["t_dispose"] if r["t_dispose"] is not None else r["t_release"]
        if t_izb is None or t_izb < t_sker: t_izb = t_sker
        tips = "Autobuss" if (r["tips"] or "").startswith("Bus") else "Auto"
        marsruts = r["marsruts"] or "Nezinams"
        gaid_s = round(gaid_min * 60.0, 2)
        apstajas = "Ja" if gaid_s > 0.5 else "Ne"
        for akt, t in [("Ierasanas krustojuma", t_ier),
                       ("Gaidisana pie luksofora", t_que),
                       ("Krustojuma skersosana", t_sker),
                       ("Izbrauksana no krustojuma", t_izb)]:
            rindas.append({"case_id": eid, "activity": akt,
                "timestamp": (BAZES_DATUMS + timedelta(minutes=t)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                "marsruts": marsruts, "transporta_veids": tips,
                "gaidisanas_laiks_s": gaid_s, "apstajas_pie_luksofora": apstajas})
    rindas.sort(key=lambda x: (x["case_id"], x["timestamp"]))
    return rindas, izlaisti

def main():
    entiti = parse_trase(IEEJAS_FAILS)
    rindas, izlaisti = veido_event_log(entiti)
    lauki = ["case_id","activity","timestamp","marsruts","transporta_veids","gaidisanas_laiks_s","apstajas_pie_luksofora"]
    with open(IZEJAS_FAILS,"w",newline="",encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=lauki); w.writeheader(); w.writerows(rindas)
    gadijumi = sorted({x["case_id"] for x in rindas})
    print(f"Entitiji kopa:                {len(entiti)}")
    print(f"Izlaisti (ne-transportlidz.): {izlaisti}")
    print(f"Transportlidzekli (gadijumi): {len(gadijumi)}")
    print(f"Notikumu rindas:              {len(rindas)}")
    marsr, veidi, apst, seen = Counter(), Counter(), Counter(), set()
    for x in rindas:
        if x["case_id"] in seen: continue
        seen.add(x["case_id"])
        marsr[x["marsruts"]] += 1; veidi[x["transporta_veids"]] += 1; apst[x["apstajas_pie_luksofora"]] += 1
    print("Pa marsrutiem:", dict(sorted(marsr.items())))
    print("Pa veidiem:   ", dict(veidi))
    print("Apstajas pie luksofora:", dict(apst))
    print(f"Saglabats: {IZEJAS_FAILS}")

if __name__ == "__main__":
    main()
