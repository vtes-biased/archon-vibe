# TWDA event reconciliation

Read-only output of `backend/scripts/reconcile_twda.py`. Deleted with the
board line that owns it.

| outcome | entries |
|---|---|
| attach — vekn id | 2177 |
| attach — winner+date | 1174 |
| create — no candidate | 1136 |
| review — 2 candidates | 36 |
| attach — winner+date+name | 11 |
| review — own link resolves to nothing | 2 |
| attach — own link | 1 |
| review — vekn id contested | 1 |

**1136 entries have no candidate** and are the reconstruction.
**39 need a human.**

## Review queue

| twda id | date | winner | twda event | why | candidates |
|---|---|---|---|---|---|
| 12797 | 2025-11-15 | Tiago Gonçalves | Bloodshed in VdC | vekn id contested | 'delete me'@2025-11-15 'Bloodshed in VdC'@2025-11-15 |
| 2010ecday1 | 2010-10-30 | Erik Torstensson | EC 2010 Day 1 | 2 candidates | 'Legendary Vampire 2010'@2010-10-29 'Day 1 3rd Group'@2010-10-30 |
| 2010eclegvam | 2010-10-29 | Erik Torstensson | EC 2010 Legendary Vampire | 2 candidates | 'Legendary Vampire 2010'@2010-10-29 'Day 1 3rd Group'@2010-10-30 |
| 2010originsthu1 | 2010-06-24 | Hugh Angseesing | Origins Thursday MQ 11am | 2 candidates | 'Origins Thurs AM'@2010-06-24 'Origins Thurs PM'@2010-06-24 |
| 2010originsthu2 | 2010-06-24 | Hugh Angseesing | Origins Thursday MQ 5pm | 2 candidates | 'Origins Thurs AM'@2010-06-24 'Origins Thurs PM'@2010-06-24 |
| 2010pwbla1 | 2010-05-29 | Darby Keeney | Powerbase: Los Angeles Event #1 | 2 candidates | 'Strategicon - Gamex 2010 - Powerbase: Los Angeles Continental Qualifier (Event #2)'@2010-05-29 'Strategicon - Gamex 2010 - Powerbase: Los Angeles Mini-Qualifier (Event #3)'@2010-05-30 |
| 2010pwblaQ | 2010-05-29 | Darby Keeney | Powerbase: Los Angeles Event #2 | 2 candidates | 'Strategicon - Gamex 2010 - Powerbase: Los Angeles Continental Qualifier (Event #2)'@2010-05-29 'Strategicon - Gamex 2010 - Powerbase: Los Angeles Mini-Qualifier (Event #3)'@2010-05-30 |
| 2013jbflac | 2013-05-25 | Robert Goudie | Jann Berger's "F" is for Flash | 2 candidates | 'Jann Berger\'s "F" is for Flash - Gamex 2013 - Event #2'@2013-05-25 'Jann Berger\'s "H" is for Haymaker - Gamex 2013 - Event #4'@2013-05-26 |
| 2013jbhlac | 2013-05-26 | Robert Goudie | Jann Berger's "H" is for Haymaker | 2 candidates | 'Jann Berger\'s "F" is for Flash - Gamex 2013 - Event #2'@2013-05-25 'Jann Berger\'s "H" is for Haymaker - Gamex 2013 - Event #4'@2013-05-26 |
| 2014avoeccqba | 2014-04-26 | Simon Reed | Australian VTES Open Event CCQ | 2 candidates | 'Brisbane 2014 Continental Qualifier'@2014-04-25 '2014 Australian VTES Open Event'@2014-04-26 |
| 2014bccqba | 2014-04-25 | Simon Reed | Brisbane CCQ | 2 candidates | 'Brisbane 2014 Continental Qualifier'@2014-04-25 '2014 Australian VTES Open Event'@2014-04-26 |
| 2k4originssaturday | 2004-06-26 | Ben Peal | Origins Saturday - NAC Qualifier | 2 candidates | 'Imported VTES Event'@2004-06-26 'Imported VTES Event'@2004-06-27 |
| 2k4originssunday | 2004-06-27 | Ben Peal | Origins Sunday | 2 candidates | 'Imported VTES Event'@2004-06-26 'Imported VTES Event'@2004-06-27 |
| 2k5originssat | 2005-07-02 | Chris Berg | Origins Saturday - NAC Qualifier | 2 candidates | 'Imported VTES Event'@2005-07-01 'Imported VTES Event'@2005-07-02 |
| 2k5originsthur10 | 2005-06-30 | Ben Peal | Origins Thursday 10am | 2 candidates | 'Imported VTES Event'@2005-06-30 'Imported VTES Event'@2005-06-30 |
| 2k5originsthur4 | 2005-06-30 | Ben Peal | Origins Thursday 4pm | 2 candidates | 'Imported VTES Event'@2005-06-30 'Imported VTES Event'@2005-06-30 |
| 2k6eclcq | 2006-11-25 | Ruben Feldman | EC 2006 Day 1 | 2 candidates | 'Last Chance EQ - Torino'@2006-11-24 'European Championship 2006 - Day 1'@2006-11-25 |
| 2k6lcqectorino | 2006-11-24 | Ruben Feldman | EC 2006 - Last Chance Qualifier | 2 candidates | 'Last Chance EQ - Torino'@2006-11-24 'European Championship 2006 - Day 1'@2006-11-25 |
| 2k6originsthu7 | 2006-06-29 | Ben Peal | Origins Thursday 7pm | 2 candidates | 'Origins 9am'@2006-06-29 'Origins 7pm'@2006-06-29 |
| 2k6originsthu9 | 2006-06-29 | Ben Peal | Origins Thursday 9am | 2 candidates | 'Origins 9am'@2006-06-29 'Origins 7pm'@2006-06-29 |
| 2k7losangelesqual | 2007-05-26 | Darby Keeney | SoCal 2007 Qualifier | 2 candidates | 'Powerbase: Los Angeles #2 (Qualifier)'@2007-05-26 'Powerbase: Los Angeles #3'@2007-05-27 |
| 2k7originssat | 2007-07-07 | Ben Peal | Origins Saturday - NAC Qualifier | 2 candidates | 'Origins NAQ'@2007-07-07 '7-8 Constructed'@2007-07-08 |
| 2k7originssun | 2007-07-08 | Ben Peal | Origins Sunday | 2 candidates | 'Origins NAQ'@2007-07-07 '7-8 Constructed'@2007-07-08 |
| 2k7qcfmetz | 2007-05-27 | Pierre Tran-Van | French NCQ - Spirit Marionette | 2 candidates | 'Hand Contract'@2007-05-26 'QCF Metz'@2007-05-27 |
| 2k8ECQCannes | 2008-02-16 | Pierre Denis Brouillet | Special International ECQ | 2 candidates | 'Special QCE Cannes'@2008-02-16 'VTES on the Red Carpet'@2008-02-17 |
| 2k8gencon | 2008-08-16 | Jonathan Scherer | NAC 2008 | 2 candidates | 'V:TES Standard Constructed'@2008-08-15 'U.S.A. National Championship'@2008-08-16 |
| 2k8miniECQCannes | 2008-02-17 | Pierre Denis Brouillet | Mini-ECQ | 2 candidates | 'Special QCE Cannes'@2008-02-16 'VTES on the Red Carpet'@2008-02-17 |
| 2k8originsfridayam | 2008-06-27 | Hugh Angseesing | Origins Friday 11am | 2 candidates | '06/27 11am Constructed'@2008-06-27 '06/27 6pm Constructed'@2008-06-27 |
| 2k8originsfridaypm | 2008-06-27 | Hugh Angseesing | Origins Friday 6pm | 2 candidates | '06/27 11am Constructed'@2008-06-27 '06/27 6pm Constructed'@2008-06-27 |
| 2k8pwbsla2 | 2008-05-24 | Ira Fay | Powerbase: Los Angeles Event #2 - NAC Qualifier | 2 candidates | 'The Large Bowl Sat AM'@2008-05-24 'NAQ Los Angeles 08'@2008-05-24 |
| 2k9grenobleqce | 2009-05-17 | Yannick Gibert | French ECQ | 2 candidates | 'QCF 2009 Grenoble'@2009-05-16 'Grenoble European Qualifier'@2009-05-17 |
| 2k9grenobleqcf | 2009-05-16 | Yannick Gibert | French NCQ | 2 candidates | 'QCF 2009 Grenoble'@2009-05-16 'Grenoble European Qualifier'@2009-05-17 |
| 2k9italychamp | 2009-05-31 | Simone Bianchi | Italian NC 2009 | 2 candidates | 'Lunatic Eruption'@2009-05-30 'Campionato Italiano 2009'@2009-05-31 |
| 2k9ofcolumbus | 2009-06-24 | Robyn Tatu | Old Friends MQ | 2 candidates | 'Old Friends: Columbus'@2009-06-24 'Origins Constructed #1'@2009-06-25 |
| 2k9origins1 | 2009-06-25 | Robyn Tatu | Origins Thursday 11am | 2 candidates | 'Old Friends: Columbus'@2009-06-24 'Origins Constructed #1'@2009-06-25 |
| 2k9pbla1 | 2009-05-23 | Dennis Lien | Powerbase: Los Angeles Event #1 | 2 candidates | 'Powerbase: L.A. #1'@2009-05-23 'Powerbase: L.A. Mini Q'@2009-05-24 |
| 2k9pbla4 | 2009-05-24 | Dennis Lien | Powerbase: Los Angeles Event #4 - MQ | 2 candidates | 'Powerbase: L.A. #1'@2009-05-23 'Powerbase: L.A. Mini Q'@2009-05-24 |
| 344c750a-6ac8-4bb7-bb01-d704dae96ff1 | 2025-12-20 | Simone Parmeggiani | Bleeding for Christmas | own link resolves to nothing |  |
| a02710a7-6db1-4686-97a7-7a40052bfbce | 2025-12-28 | Jose Vte Coll | Valencia Bloody Christmas | own link resolves to nothing |  |
