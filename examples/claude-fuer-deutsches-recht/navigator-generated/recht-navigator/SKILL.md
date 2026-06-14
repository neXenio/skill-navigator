---
name: recht-navigator
description: >
  recht-navigator: decision-tree entry point. Top areas: Krankenversicherung Krankenkassenrecht, Mietrecht Krankenhausrecht, Pruefer Abgleich, Verteidiger Vertragsrecht, Fachanwalt Familienrecht, Kompass Sprache, Kanzlei Builder, Hochschulrecht Bundesnetzagentur, Pruefer Ecommerce, Gesellschaftsrecht Corporate, Datenschutzrecht Datenbankrecht, Berufsrecht Vertragspruefung, Patentrecht Seerecht, Praxis Leasingrecht, Praxis Handelsregister, Pruefer Schriftform. Answer the question, pick an area, load its SKILL.md, navigate down to the matching leaf skill.
user-invokable: true
args:
  - name: skill
    description: >
      Direct sub-skill to load. Available: "wing-krankenversicherung-krankenkassenrecht", "wing-mietrecht-krankenhausrecht", "wing-pruefer-abgleich", "wing-verteidiger-vertragsrecht", "wing-fachanwalt-familienrecht", "wing-kompass-sprache", "wing-kanzlei-builder", "wing-hochschulrecht-bundesnetzagentur", "wing-pruefer-ecommerce", "wing-gesellschaftsrecht-corporate", "wing-datenschutzrecht-datenbankrecht", "wing-berufsrecht-vertragspruefung", "wing-patentrecht-seerecht", "wing-praxis-leasingrecht", "wing-praxis-handelsregister", "wing-pruefer-schriftform".
    required: false
metadata:
  category: "router"
  kind: "root"
  navigator: "true"
---

# Entscheidungsknoten: recht-navigator  (Bereich)

Leitet zu 1 von 1 Unterskills. Lies das gewaehlte Unterskill vollstaendig, bevor du handelst.

## Frage

Waehle den passenden Unterbereich von «recht-navigator». Lade dessen SKILL.md; weiter bis zum Blatt (Einzelskill).

## Zweige
- **Pruefer Abgleich**: Stichworte: pruefer, abgleich, fortbestehensprognose, strafzumessung, verfassungsrecht -> `wing-pruefer-abgleich/SKILL.md`

## Wenn unklar
- Mehrere passen -> nenne Kandidaten, frage Nutzer.
- Keiner passt -> gehe HOCH (Link «Eine Ebene hoeher») und nimm einen Nachbarzweig. Erst an der Wurzel den Nutzer um Praezisierung bitten.
