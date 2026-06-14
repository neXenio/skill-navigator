---
name: wing-pruefer-abgleich
description: >
  Entscheidungsknoten (Bereich) Pruefer Abgleich -> Abgleich Gebrauchsmusterrecht Strafzumessung, Hausverwaltung Insolvenzforderungsanmeldungspruefung Aktienrecht, Zwangsvollstreckung Zwangsverwaltung Insolvenzverwaltung.
user-invokable: false
args:
  - name: skill
    description: >
      Direct sub-skill to load. Available: "room-abgleich-gebrauchsmusterrecht-strafzumessung", "room-hausverwaltung-insolvenzforderungsanmeldungspruefung-aktienr", "room-zwangsvollstreckung-zwangsverwaltung-insolvenzverwaltung".
    required: false
metadata:
  category: "router"
  kind: "wing"
  navigator: "true"
---

# Entscheidungsknoten: Pruefer Abgleich  (Bereich)

Leitet zu 1 von 1 Unterskills. Lies das gewaehlte Unterskill vollstaendig, bevor du handelst.

## Frage

Waehle den passenden Unterbereich von «Pruefer Abgleich». Lade dessen SKILL.md; weiter bis zum Blatt (Einzelskill).

## Zweige
- **Abgleich Gebrauchsmusterrecht Strafzumessung**: Stichworte: abgleich, gebrauchsmusterrecht, strafzumessung, pruefer, prozessrecht -> `room-abgleich-gebrauchsmusterrecht-strafzumessung/SKILL.md`

## Eine Ebene hoeher

Passt kein Zweig? Gehe zurueck zu: `../SKILL.md`



## Wenn unklar
- Mehrere passen -> nenne Kandidaten, frage Nutzer.
- Keiner passt -> gehe HOCH (Link «Eine Ebene hoeher») und nimm einen Nachbarzweig. Erst an der Wurzel den Nutzer um Praezisierung bitten.
