"""Genera una lista M3U dei canali italiani gratuiti con ID compatibili con la guida TV.

Sorgenti:
  - canali:   https://iptv-org.github.io/iptv/countries/it.m3u
  - guida TV: https://iptv-epg.org/files/epg-it.xml.gz

La lista iptv-org usa tvg-id con suffisso (es. "Rai1.it@SD"), mentre la guida usa
"Rai1.it": senza correzione Kodi (IPTV Simple Client) non abbina i programmi.
Lo script toglie il suffisso, abbina per nome i canali rimasti scoperti,
esclude i canali a pagamento e scrive dist/it.m3u.
"""

import gzip
import json
import re
import sys
import urllib.request
from pathlib import Path

M3U_URL = "https://iptv-org.github.io/iptv/countries/it.m3u"
EPG_URL = "https://iptv-epg.org/files/epg-it.xml.gz"
# Guida unita (italiana + tematici) pubblicata accanto alla lista.
MERGED_EPG_URL = "https://papaito-altoriso.github.io/kodi-iptv-it/epg.xml.gz"

# Canali a pagamento: nella lista pubblica possono comparire flussi non autorizzati.
PAY_PREFIXES = (
    "sky ",
    "eurosport",
    "cartoon network",
    "dea kids",
    "disney channel",
    "sky sport",
)


# ID iptv-org (senza suffisso) -> ID della guida, dove i nomi non coincidono.
ALIASES = {
    "rainews24.it": "RaiNews.it",
    "20.it": "Mediaset20.it",
    "twentyseven.it": "Mediaset27Twentyseven.it",
    "discoverychannel.it": "Discovery.it",
    "rtl1025tv.it": "RTL1025.it",
    "radiomontecarlotv.it": "RadioMonteCarlo.it",
}


# Numerazione del digitale terrestre (LCN): nome normalizzato -> numero.
LCN = {
    "rai1": 1, "rai2": 2, "rai3": 3, "rete4": 4, "canale5": 5, "italia1": 6,
    "la7": 7, "tv8": 8, "nove": 9,
    "20": 20, "rai4": 21, "iris": 22, "rai5": 23, "raimovie": 24,
    "raipremium": 25, "cielo": 26, "twentyseven": 27, "tv2000": 28,
    "la7d": 29, "la5": 30, "realtime": 31, "qvc": 32, "foodnetwork": 33,
    "cine34": 34, "focus": 35, "rtl1025tv": 36, "giallo": 38, "topcrime": 39,
    "boing": 40, "k2": 41, "raigulp": 42, "raiyoyo": 43, "frisbee": 44,
    "cartoonito": 46, "super": 47, "rainews24": 48, "skytg24": 50,
    "tgcom24": 51, "dmax": 52, "raistoria": 54, "mediasetextra": 55,
    "hgtv": 56, "raiscuola": 57, "raisport": 58, "motortrend": 59,
    "sportitalia": 60,
}
OTHER_START = 100  # gli altri canali partono da qui, nell'ordine della lista


def lcn_key(name: str) -> str:
    n = re.sub(r"\(.*?\)|\[.*?\]", " ", name.lower())
    n = re.sub(r"\s+hd\s*$", " ", n.strip())
    return re.sub(r"[^a-z0-9]", "", n)


def quality(name: str) -> tuple:
    """Più alto = meglio: non geobloccato, attivo 24/7, risoluzione maggiore."""
    res = re.search(r"\((\d{3,4})p\)", name)
    return (
        "geo-blocked" not in name.lower(),
        "not 24/7" not in name.lower(),
        int(res.group(1)) if res else 0,
    )


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "kodi-iptv-it/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def norm(name: str) -> str:
    """Nome confrontabile: senza qualità, tag, prefisso paese, 'HD' e punteggiatura."""
    n = name.lower()
    n = re.sub(r"\(.*?\)|\[.*?\]", " ", n)
    n = re.sub(r"^\s*it\s*-\s*", " ", n)
    n = re.sub(r"\b(hd|fhd|sd|italia|italy)\b", " ", n)
    return re.sub(r"[^a-z0-9]", "", n)


# Canali tematici internazionali: (gruppo, primo numero, [ID canale iptv-org]).
THEMATIC = [
    ("Droni e natura", 900, [
        "DroneTV.us", "MyZenTV.fr", "ZenLIFEbyStingray.ca", "SpaceLivepoweredbysen.uk",
        "WildEarth.za", "WaypointTV.us",
    ]),
    ("Moda e lifestyle", 910, [
        "FashionTVParisLOriginal.fr", "FashionTVSecrets.fr", "FashionTVEurope.fr",
        "GlobalFashionChannel.us", "30ALuxeLifeDiscovered.us",
        "SoReal.us", "INFAST.nl", "Revry.us", "RevryQueer.us", "BizTV.us",
        "SmartLifeStyleTV.us", "AntiquesRoadTrip.us", "TheJamieOliverChannel.us",
    ]),
    ("Design e arte", 930, [
        "TheDesignNetwork.us", "apartTV.lu", "BBCHomeGarden.us",
        "ClassicArtsShowcase.us", "ARTFLIXMovieClassics.us",
    ]),
    ("Viaggi", 950, ["AutenticTravel.de"]),
    ("Documentari e cultura", 960, [
        "BBCEarth.uk", "BBCFour.uk", "FlowersTVUSA.us", "FoxSoul.us",
        "MBCAmerica.us", "MedTV.mt", "DDMizoram.in",
    ]),
    ("Notizie", 980, ["EuronewsItalian.fr"]),
]
STREAMS_URL = "https://iptv-org.github.io/api/streams.json"
# Solo flussi da piattaforme di distribuzione ufficiali (FAST/CDN), non restream.
OFFICIAL_HOSTS = re.compile(
    r"wurl\.tv|amagi\.tv|mediatailor|teleosmedia|aniview|evrideo|streamhoster"
    r"|30a-tv\.com|akamaized\.net|cloudfront\.net|cdn-redge\.media"
    r"|rakuten\.tv|stingray\.com|frequency\.stream"
)


def works(stream: dict) -> bool:
    """Il flusso risponde con una playlist HLS?"""
    headers = {"User-Agent": stream.get("user_agent") or "Mozilla/5.0"}
    if stream.get("referrer"):
        headers["Referer"] = stream["referrer"]
    try:
        req = urllib.request.Request(stream["url"], headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            return b"#EXTM3U" in r.read(2000)
    except Exception:
        return False


def thematic() -> tuple:
    """Righe M3U dei canali tematici e la lista (tvg-id, nome) per la guida."""
    streams = json.loads(fetch(STREAMS_URL))
    by_channel = {}
    for s in streams:
        if s.get("channel") and OFFICIAL_HOSTS.search(s.get("url", "")):
            by_channel.setdefault(s["channel"], []).append(s)
    out, chans = [], []
    for group, start, ids in THEMATIC:
        num = start
        for cid in ids:
            cands = by_channel.get(cid)
            if not cands:
                continue
            cands.sort(key=lambda s: -int((s.get("quality") or "0p").rstrip("pi") or 0))
            s = next((c for c in cands if works(c)), None)
            if s is None:
                continue
            name = s.get("title") or cid.split(".")[0]
            out.append(
                f'#EXTINF:-1 tvg-chno="{num}" tvg-id="{cid}" group-title="{group}",{name}'
            )
            if s.get("user_agent"):
                out.append(f"#EXTVLCOPT:http-user-agent={s['user_agent']}")
            if s.get("referrer"):
                out.append(f"#EXTVLCOPT:http-referrer={s['referrer']}")
            out.append(s["url"])
            chans.append((cid, name))
            num += 1
    print(f"canali tematici: {len(chans)}")
    return out, chans


# Guide pubbliche per i canali tematici (piattaforme FAST e iptv-epg).
EXTRA_EPG_URLS = [
    "https://i.mjh.nz/Plex/all.xml.gz",
    "https://i.mjh.nz/PlutoTV/all.xml.gz",
    "https://i.mjh.nz/SamsungTVPlus/all.xml.gz",
    "https://i.mjh.nz/Roku/all.xml.gz",
    "https://iptv-epg.org/files/epg-fr.xml.gz",
    "https://iptv-epg.org/files/epg-gb.xml.gz",
]
# Nome con cui cercare il canale nelle guide; None = non cercare (feed diversi
# con lo stesso nome darebbero orari sbagliati).
EPG_NAMES = {
    "ZenLIFEbyStingray.ca": "ZenLIFE",
    "SpaceLivepoweredbysen.uk": "Space Live",
    "TheJamieOliverChannel.us": "Jamie Oliver",
    "ARTFLIXMovieClassics.us": "Artflix",
    "30ALuxeLifeDiscovered.us": "30A Luxe Life",
    "SmartLifeStyleTV.us": None,
    "FashionTVParisLOriginal.fr": None,
    "FashionTVSecrets.fr": None,
    "FashionTVEurope.fr": None,
}


def extra_epg(chans: list) -> str:
    """Canali e programmi dei tematici presi dalle guide esterne, con il tvg-id della lista."""
    import xml.etree.ElementTree as ET

    wanted = {}
    for cid, name in chans:
        search = EPG_NAMES.get(cid, name)
        if search:
            wanted[cid] = norm_epg(search)

    def matches(display: str) -> list:
        d = norm_epg(display)
        return [cid for cid, w in wanted.items() if d == w or (len(w) > 5 and w in d and len(d) < len(w) + 12)]

    progs = {}  # (nostro id, id sorgente) -> [xml programma]
    for url in EXTRA_EPG_URLS:
        try:
            raw = gzip.decompress(fetch(url))
        except Exception as e:
            print(f"guida saltata {url}: {e}")
            continue
        src = {}  # id sorgente -> nostri id
        for _, el in ET.iterparse(__import__("io").BytesIO(raw), events=("end",)):
            if el.tag == "channel":
                for dn in el.findall("display-name"):
                    for cid in matches(dn.text or ""):
                        src.setdefault(el.get("id"), set()).add(cid)
                el.clear()
            elif el.tag == "programme":
                for cid in src.get(el.get("channel"), ()):
                    el2 = ET.fromstring(ET.tostring(el))
                    el2.set("channel", cid)
                    progs.setdefault((cid, url + el.get("channel")), []).append(ET.tostring(el2, encoding="unicode"))
                el.clear()
        del raw

    parts, covered = [], 0
    for cid, name in chans:
        best = max((v for k, v in progs.items() if k[0] == cid), key=len, default=None)
        if not best:
            continue
        covered += 1
        parts.append(f'<channel id="{cid}"><display-name>{escape(name)}</display-name></channel>')
        parts += best
    print(f"guida per canali tematici: {covered} su {len(chans)}")
    return "\n".join(parts)


def norm_epg(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main() -> int:
    m3u = fetch(M3U_URL).decode("utf-8")
    epg = gzip.decompress(fetch(EPG_URL)).decode("utf-8", "replace")

    epg_ids = {}  # minuscolo -> id originale
    epg_by_name = {}  # nome normalizzato -> id
    for cid, body in re.findall(r'<channel id="([^"]*)">(.*?)</channel>', epg, re.S):
        epg_ids[cid.lower()] = cid
        for dn in re.findall(r"<display-name[^>]*>([^<]*)<", body):
            epg_by_name.setdefault(norm(dn), cid)

    lines = m3u.splitlines()
    entries = []  # (nome, riga EXTINF, url)
    kept = matched = dropped = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("#EXTINF"):
            i += 1
            continue
        # Dopo #EXTINF possono esserci righe di opzioni (#EXTVLCOPT, #KODIPROP…)
        # prima dell'indirizzo: le teniamo insieme all'indirizzo.
        i += 1
        extra = []
        while i < len(lines) and lines[i].startswith("#") and not lines[i].startswith("#EXTINF"):
            extra.append(lines[i])
            i += 1
        if i >= len(lines) or lines[i].startswith("#"):
            continue
        url = "\n".join(extra + [lines[i]])
        i += 1
        name = line.rsplit(",", 1)[-1].strip()
        if norm(name) == "" or name.lower().startswith(PAY_PREFIXES):
            dropped += 1
            continue

        m = re.search(r'tvg-id="([^"]*)"', line)
        tid = m.group(1) if m else ""
        base = tid.split("@", 1)[0]
        new_id = (
            ALIASES.get(base.lower())
            or epg_ids.get(base.lower())
            or epg_by_name.get(norm(name))
            or base
        )
        if new_id.lower() in epg_ids:
            matched += 1
        if m:
            line = line.replace(m.group(0), f'tvg-id="{new_id}"')
        else:
            line = line.replace("#EXTINF:-1", f'#EXTINF:-1 tvg-id="{new_id}"', 1)
        entries.append((name, line, url, new_id, tid))
        kept += 1

    # Per ogni numero LCN tiene la versione migliore del canale; i doppioni
    # (SD/HD, geobloccati, regionali) finiscono tra gli altri dal 100 in poi.
    best = {}
    for idx, (name, *_) in enumerate(entries):
        num = LCN.get(lcn_key(name))
        if num and (num not in best or quality(name) > quality(entries[best[num]][0])):
            best[num] = idx
    chno = {idx: num for num, idx in best.items()}
    nxt = OTHER_START
    for idx in range(len(entries)):
        if idx not in chno:
            chno[idx] = nxt
            nxt += 1

    out = [f'#EXTM3U x-tvg-url="{MERGED_EPG_URL}"']
    # Kodi usa tvg-id come identificativo del canale: due canali con lo stesso
    # tvg-id vengono fusi in uno. Il primo (quello numerato) tiene l'ID della
    # guida, i doppioni tornano all'ID originale con suffisso (es. Rai2.it@HD).
    used = set()
    for idx in sorted(chno, key=chno.get):
        name, line, url, new_id, orig_id = entries[idx]
        if new_id.lower() in used and orig_id:
            line = line.replace(f'tvg-id="{new_id}"', f'tvg-id="{orig_id}"', 1)
        used.add(new_id.lower())
        line = re.sub(r'\s*tvg-chno="[^"]*"', "", line)
        line = line.replace("#EXTINF:-1", f'#EXTINF:-1 tvg-chno="{chno[idx]}"', 1)
        out += [line, url]

    if kept < 50:
        print(f"Troppo pochi canali ({kept}): sorgente probabilmente rotta, non scrivo.")
        return 1

    th_chans = []
    try:
        th_lines, th_chans = thematic()
        out += th_lines
    except Exception as e:  # i tematici non devono mai bloccare la lista principale
        print(f"Canali tematici saltati: {e}")

    # Guida unica: quella italiana più i programmi dei tematici trovati altrove.
    extra = ""
    try:
        extra = extra_epg(th_chans)
    except Exception as e:
        print(f"Guida dei tematici saltata: {e}")
    head, _, _ = epg.rpartition("</tv>")
    merged = head + extra + "\n</tv>\n"

    dist = Path(__file__).parent / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "it.m3u").write_text("\n".join(out) + "\n", encoding="utf-8")
    (dist / "epg.xml.gz").write_bytes(gzip.compress(merged.encode("utf-8")))
    print(f"canali: {kept}, con guida TV: {matched}, esclusi (a pagamento): {dropped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
