# TWDA event reconciliation

Read-only output of `backend/scripts/reconcile_twda.py`. Deleted with the
board line that owns it.

Run 2026-08-16 against 8475 live tournaments and 4538 TWDA entries. The archive grows weekly — re-run before acting on a stale queue.

| outcome | entries |
|---|---|
| attach — vekn id | 2177 |
| attach — winner+date | 1171 |
| create — no candidate | 1136 |
| attach — winner+date+size | 28 |
| attach — winner+date+name | 11 |
| review — 2 candidates | 8 |
| attach — own link | 3 |
| review — target claimed by another entry | 3 |
| review — vekn id contested | 1 |

**1136 entries have no candidate** and are the reconstruction.
**12 need a human.**

## Review queue

| twda id | date | winner | twda event | why | candidates |
|---|---|---|---|---|---|
| 11429 | 2024-06-01 | Martin Weinmayer | Blood League part IV. (12p) | target claimed by another entry | `019f1a1a-427c` 'Breath of the Dragon'@2024-06-02/24p |
| 12797 | 2025-11-15 | Tiago Gonçalves | Bloodshed in VdC (10p) | vekn id contested | `abd7e330-8005` 'delete me'@2025-11-15/0p `019f1a1a-ba64` 'Bloodshed in VdC'@2025-11-15/11p |
| 2010ecday1 | 2010-10-30 | Erik Torstensson | EC 2010 Day 1 (155p) | 2 candidates | `019f1a07-834f` 'Legendary Vampire 2010'@2010-10-29/25p `019f1a07-70ec` 'Day 1 3rd Group'@2010-10-30/39p |
| 2010originsthu2 | 2010-06-24 | Hugh Angseesing | Origins Thursday MQ 5pm (28p) | 2 candidates | `019f1a18-5c3f` 'Origins Thurs AM'@2010-06-24/24p `019f1a07-7ab5` 'Origins Thurs PM'@2010-06-24/29p |
| 2010pwblaQ | 2010-05-29 | Darby Keeney | Powerbase: Los Angeles Event #2 (15p) | 2 candidates | `019f1a07-7811` 'Strategicon - Gamex 2010 - Powerbase: Los Angeles Continental Qualifier (Event #2)'@2010-05-29/14p `019f1a07-834a` 'Strategicon - Gamex 2010 - Powerbase: Los Angeles Mini-Qualifier (Event #3)'@2010-05-30/12p |
| 2010shfsd1 | 2010-08-21 | Jason Ryan | SuperHappyFunSlide Day 1 (19p) | target claimed by another entry | `019f1a07-789f` 'VTES Super Happy Funslide Weekend: Day One'@2010-08-21/18p |
| 2010shfsd2 | 2010-08-22 | Jason Ryan | SuperHappyFunSlide Day 2 (19p) | target claimed by another entry | `019f1a07-789f` 'VTES Super Happy Funslide Weekend: Day One'@2010-08-21/18p |
| 2013jbflac | 2013-05-25 | Robert Goudie | Jann Berger's "F" is for Flash (13p) | 2 candidates | `019f1a18-aabd` 'Jann Berger\'s "F" is for Flash - Gamex 2013 - Event #2'@2013-05-25/12p `019f1a18-aaaf` 'Jann Berger\'s "H" is for Haymaker - Gamex 2013 - Event #4'@2013-05-26/10p |
| 2k5originssat | 2005-07-02 | Chris Berg | Origins Saturday - NAC Qualifier (25p) | 2 candidates | `019f1a07-4718` 'Imported VTES Event'@2005-07-01/22p `019f1a05-f050` 'Imported VTES Event'@2005-07-02/35p |
| 2k5originsthur4 | 2005-06-30 | Ben Peal | Origins Thursday 4pm (12p) | 2 candidates | `019f1a07-2d4d` 'Imported VTES Event'@2005-06-30/13p `019f1a06-b85c` 'Imported VTES Event'@2005-06-30/24p |
| 2k7losangelesqual | 2007-05-26 | Darby Keeney | SoCal 2007 Qualifier (12p) | 2 candidates | `019f1a06-cfaa` 'Powerbase: Los Angeles #2 (Qualifier)'@2007-05-26/13p `019f1a06-19b2` 'Powerbase: Los Angeles #3'@2007-05-27/9p |
| 2k9italychamp | 2009-05-31 | Simone Bianchi | Italian NC 2009 (27p) | 2 candidates | `019f1a01-cddc` 'Lunatic Eruption'@2009-05-30/22p `019f1a05-cd31` 'Campionato Italiano 2009'@2009-05-31/26p |
