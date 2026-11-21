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
import re
import sys
import urllib.request
from pathlib import Path

M3U_URL = "https://iptv-org.github.io/iptv/countries/it.m3u"
EPG_URL = "https://iptv-epg.org/files/epg-it.xml.gz"

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
    out = [f'#EXTM3U x-tvg-url="{EPG_URL}"']
    kept = matched = dropped = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("#EXTINF"):
            i += 1
            continue
        url = lines[i + 1] if i + 1 < len(lines) else ""
        i += 2
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
        out += [line, url]
        kept += 1

    if kept < 50:
        print(f"Troppo pochi canali ({kept}): sorgente probabilmente rotta, non scrivo.")
        return 1

    dist = Path(__file__).parent / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "it.m3u").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"canali: {kept}, con guida TV: {matched}, esclusi (a pagamento): {dropped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
