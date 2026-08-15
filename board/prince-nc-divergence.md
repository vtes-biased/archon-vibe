> Elaborated context for a line in `BOARD.md`. Deleted with the line.
> `#N` below is a **retired tracker number**, not a GitHub issue and not a live
> pointer — the surrounding prose carries the fact. A real GitHub issue is
> written `gh-N`.

# Prince / NC divergence — legacy archon vs the app

Captured on production **2026-08-09**, while the legacy `archondb` was still live on the
box. Recorded here deliberately: the final archive dump retires that database, and after
that this comparison cannot be reproduced.

**This is a review queue, not a backfill plan.** Prince and NC are app-managed — archon is
the system of record for them. Legacy archon mirrored vekn.net's `princeid`/`coordinatorid`;
appointments have moved on since, and the app has been managing them since the cutover. So a
name below may mean "we lost this at migration" *or* "this person stepped down and the app is
right". Only someone who knows the appointments can tell those apart.

Why it was excluded from the judge-rank backfill (see `569-legacy-role-backfill.md`): a union
can only ADD. Restoring a superseded Prince republishes their contact details in the **public**
officials directory (`access_levels.py`:102 puts Prince/NC there), and the two NC candidates
are in countries that already have a different, current NC — a blind union would seat two
national coordinators. The judge ranks were safe precisely because they diverged in only one
direction and confer no access.

Counts: Prince legacy=465 app=472; NC 42/42.

### In legacy archon, absent in the app (candidates to review)

| VEKN | Name | Country (legacy) | Legacy role | App roles today |
|------|------|------------------|-------------|-----------------|
| 1002955 | Danilo Fernandes | Brazil | **Prince** | — |
| 1003089 | Bruno Peixoto Moreira | Brazil | **Prince** | — |
| 4590035 | Bruno Paramo Meleiro | Brazil | **Prince** | — |
| 5830013 | Guilherme "Griffo" | Brazil | **Prince** | — |
| 6020112 | Daniel Anão | Brazil | **Prince** | — |
| 6130052 | Hércules Peres | Brazil | **Prince** | — |
| 6130079 | Schwarzenneger Erick | Brazil | **Prince** | — |
| 7300093 | Raylson Oliveira | Brazil | **Prince** | — |
| 7790009 | Vinicius Costalonga | Brazil | **Prince** | — |
| 1000224 | Wes Weston | Canada | **NC** | Prince |
| 3090032 | Maros Chomjak | Czech Republic | **Prince** | — |
| 3670001 | Jesper Bøje | Denmark | **Prince** | NC |
| 1006339 | Dr Alkonyi Csaba | Hungary | **Prince** | — |
| 2020047 | Feco Ferenc Borbely | Hungary | **Prince** | — |
| 3540058 | Zsolt Cziraki | Hungary | **Prince** | — |
| 3540078 | Gabor Endler | Hungary | **Prince** | — |
| 3540099 | Sandor Kadar | Hungary | **Prince** | — |
| 3412312 | Massimo Vaccari | Italy | **Prince** | — |
| 6960007 | Stanisław Szczepaniak | Poland | **Prince** | — |
| 3030054 | Radovan Vitek | Slovakia | **Prince** | — |
| 3830065 | Antonio Calvario M | Spain | **Prince** | — |
| 8930109 | Javier Flores Álvarez | Spain | **Prince** | — |
| 8090044 | Zack Holmgren | Sweden | **Prince** | — |
| 1000595 | John Barclay | United Kingdom | **Prince** | — |
| 1000757 | Sam Marsh | United Kingdom | **Prince** | — |
| 1006550 | Steven Burnside | United Kingdom | **Prince** | — |
| 8230009 | James Freimuller | United Kingdom | **Prince** | NC |
| 2050008 | Matthew Hirsch | United States | **Prince** | — |
| 2120044 | Mark Loughman | United States | **NC** | Prince |

_29 members._

### In the app, absent in legacy archon (granted since, or appointed after legacy froze)

| VEKN | Name | App role not in legacy | App roles today |
|------|------|------------------------|-----------------|
| 8840000 | Alexandre Bustros | **NC** | NC |
| 2050001 | Ben Peal | **NC** | IC, NC |
| 4420000 | Csaba Pál | **Prince** | Prince |
| 5501907 | Daniel Lopes Padilha | **Prince** | Prince |
| 6580003 | David Fisher | **Prince** | Prince |
| 3830090 | David López-Pozuelo Rivas | **Prince** | Prince |
| 8740009 | Dennis Crowch | **Prince** | Prince |
| 4260004 | Felipe Salvador Medina Rodríguez | **Prince** | Prince |
| 7060126 | Fernando Fiorin | **Prince** | Prince |
| 7060097 | Gabriel Ivory | **Prince** | Prince |
| 5500002 | Gabriel Rodrigues de Marqui | **Prince** | Prince |
| 6130009 | Guilherme Machado | **Prince** | Prince |
| 5740004 | Guillaume Pulyk | **Prince** | Prince |
| 7400073 | Gustavo Alfonso González Ortiz | **Prince** | Prince |
| 3510120 | Jiří Stibor | **Prince** | Prince |
| 3970021 | Joakim Rapp | **Prince** | Prince |
| 8090038 | Johan Adamsson | **Prince** | Prince |
| 3540189 | Krisztián Tivadari | **Prince** | Prince |
| 6130070 | Leonardo Zimmern | **Prince** | Prince |
| 5720014 | Maarten Rijnbeek | **Prince** | Prince |
| 3260015 | Magnus Söder | **Prince** | Prince |
| 5490086 | Marcelo Cordoville Farias | **Prince** | Prince |
| 8710006 | Marcin Borowski | **Prince** | Prince |
| 8090025 | Marcus Berg | **Prince** | Prince |
| 8580010 | Marvin Lange | **Prince** | Prince |
| 6980013 | Mateusz Jarota | **Prince** | Prince |
| 3491403 | Maxime Biebaut | **Prince** | Prince |
| 7060155 | Morgana Gomes | **Prince** | Prince |
| 8365498 | Nathan Alves Bruno | **Prince** | Prince |
| 8090049 | Patrik Spjut | **Prince** | Prince |
| 3540150 | Péter Korsós | **Prince** | Prince |
| 3600016 | Robin Vossen | **Prince** | Prince |
| 1000632 | Scott Gomes | **Prince** | Prince |
| 9100001 | Simon George | **Prince** | Prince |
| 6360007 | Stefano Orlandini | **Prince** | Prince |
| 3090014 | Zsolt Varga | **Prince** | Prince |

_36 members._
