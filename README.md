# kodi-iptv-it

Lista M3U dei canali italiani gratuiti per Kodi (PVR IPTV Simple Client), con ID compatibili con la guida TV.

- Canali: [iptv-org](https://github.com/iptv-org/iptv) (`countries/it.m3u`), esclusi i canali a pagamento.
- Guida TV: [iptv-epg.org](https://iptv-epg.org) (`epg-it.xml.gz`).
- `build.py` toglie il suffisso dai `tvg-id` (`Rai1.it@SD` → `Rai1.it`) così Kodi abbina i programmi.
- GitHub Actions la rigenera ogni notte e la pubblica su GitHub Pages come `it.m3u`.

In Kodi: IPTV Simple Client → Configure → "Migrated Add-on Config"
- General → M3U playlist URL: `https://<utente>.github.io/kodi-iptv-it/it.m3u`
- EPG → XMLTV URL: `https://iptv-epg.org/files/epg-it.xml.gz`

## Canali tematici
In fondo alla lista, numerati a parte e raggruppati (`group-title`): Droni e natura (900+),
Moda e lifestyle (910+), Design e arte (930+), Viaggi (950+). Presi dall'API di iptv-org,
solo da piattaforme di distribuzione ufficiali (`OFFICIAL_HOSTS`) e solo se il flusso risponde.
