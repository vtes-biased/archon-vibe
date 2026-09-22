import type { User } from './types';
import type { TournamentListItem } from './db';
import { getCountriesOnContinent } from './geonames';
import { callEngine, getEngine } from './engine-instance';

export interface AgendaViewer {
  uid: string;
  country: string;
  continent_countries: string[];
  hidden: string[];
  added: string[];
}

export function agendaViewer(user: User | null | undefined): AgendaViewer | null {
  if (!user?.vekn_id || !user.country) return null;
  return {
    uid: user.uid,
    country: user.country,
    continent_countries: getCountriesOnContinent(user.country),
    hidden: user.agenda_hidden ?? [],
    added: user.agenda_added ?? [],
  };
}

function agendaEvent(t: TournamentListItem, playing: Set<string>) {
  return {
    uid: t.uid,
    state: t.state,
    country: t.country,
    online: t.online,
    rank: t.rank,
    organizers_uids: t.organizers_uids,
    playing: playing.has(t.uid),
  };
}

export function filterAgenda<T extends TournamentListItem>(events: T[], viewer: AgendaViewer, playing: Set<string>, includeOnline = true): T[] {
  if (events.length === 0) return [];
  const on: boolean[] = JSON.parse(callEngine(() => getEngine().agendaFilter(
    JSON.stringify(viewer), JSON.stringify(events.map(t => agendaEvent(t, playing))), includeOnline,
  )));
  return events.filter((_, i) => on[i]);
}

export function agendaToggleEntry(t: TournamentListItem, viewer: AgendaViewer, playing: Set<string>): 'hidden' | 'added' | null {
  return JSON.parse(callEngine(() => getEngine().agendaToggleEntry(JSON.stringify(viewer), JSON.stringify(agendaEvent(t, playing)))));
}
