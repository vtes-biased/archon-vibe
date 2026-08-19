import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid7

from .broadcast import broadcast_precomputed
from .data.vekn_roster import ADMINS
from .db import (
    decode_json,
    get_connection,
    get_users_by_vekn_prefix,
    get_users_with_vekn_prefix,
    get_users_without_coopted_by,
    save_user,
)
from .geonames import match_city
from .models import ObjectType, Role, User
from .vekn_api import VEKNAPIClient, VEKNAPIError

logger = logging.getLogger(__name__)


# Personal data, delivered out of band (ansible-vault at deploy, untracked dev
# copy otherwise); a missing/unreadable file skips injection silently.
def _officials_contacts_path() -> Path:
    env = os.environ.get("OFFICIALS_CONTACTS_FILE")
    if env:
        return Path(env)
    return Path(__file__).parent / "data" / "officials_contacts.json"


def _load_officials_emails() -> dict[str, str]:
    try:
        entries = json.loads(_officials_contacts_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.info("officials contacts file not present; skipping email injection")
        return {}
    except (OSError, ValueError) as e:
        # Runs at import — log and skip rather than crash backend startup.
        logger.warning("officials contacts file unreadable (%s); skipping", e)
        return {}
    return {
        e["vekn_id"]: e["email"] for e in entries if e.get("vekn_id") and e.get("email")
    }


OFFICIALS_EMAILS: dict[str, str] = _load_officials_emails()


def _derive_role_seeds(vekn_player: dict[str, Any]) -> list[Role]:
    """Roles to seed on first import only; never called again for this user."""
    roles: list[Role] = []
    if vekn_player.get("princeid"):
        roles.append(Role.PRINCE)
    if vekn_player.get("coordinatorid"):
        roles.append(Role.NC)
    vekn_id = str(vekn_player.get("veknid", ""))
    if vekn_id in ADMINS:
        roles.append(Role.IC)
    return roles


# City name corrections by country (VEKN database has typos/inconsistencies)
FIX_CITIES: dict[str, dict[str, str]] = {
    "Argentina": {
        "BUenos Aires": "Buenos Aires",
        "Buenos Aries": "Buenos Aires",
        "Capital Federal": "Buenos Aires",
    },
    "Australia": {
        "Blacktown": "Sydney",
        "Castle Hill": "Sydney",
        "Hobart (Rosny)": "Hobart",
        "Hobart, Tasmania": "Hobart",
        "Penrith": "Sydney",
        "Queanbeyan": "Canberra",
        "Ravenhall": "Melbourne",
        "Sydney (Inner City)": "Sydney",
        "Tenambit": "Maitland",
    },
    "Austria": {
        "Danube city (Vienna)": "Vienna",
        "Marchtrenk": "Linz",
        "Thalheim": "Linz",
        "Traiskirchen": "Vienna",
        "Vienna (Traiskirchen)": "Vienna",
        "Wien": "Vienna",
        "Wien/Vienna": "Vienna",
    },
    "Belarus": {"Gomel": "Homyel'"},
    "Belgium": {
        "Antwerp": "Antwerpen",
        "Bruges": "Brugge",
        "Bruxelles": "Brussels",
        "Ghent": "Gent",
        "Jodoigne": "Leuven",
        "Lige": "Liège",
        "Liege": "Liège",
    },
    "Brazil": {
        "Brasilia": "Brasília",
        "Braslia": "Brasília",
        "Campinas": "Campinas (Sao Paulo)",
        "Campogrande": "Campina Grande",
        "Canoas / Porto Alegre": "Canoas",
        "GUARULHOS": "Guarulhos",
        "Itajai": "Itajaí",
        "Imperatiz": "Imperatriz",
        "Nova Iguaçú": "Nova Iguaçu",
        "Olaria": "Rio de Janeiro",
        "Petropolis": "Petrópolis",
        "Rio De Janerio": "Rio de Janeiro",
        "Rio de Janerio": "Rio de Janeiro",
        "Rio de janeiro": "Rio de Janeiro",
        "Santo Andre": "Santo André",
        "Sao Bernardo do Campo": "São Bernardo do Campo",
        "São Luis": "São Luís",
        "São PAulo": "São Paulo",
        "So Paulo": "São Paulo",
        "Taguatinga": "Brasília",
        "Vitória / Vila Velha / Grande Vitória": "Vitória",
        "Vitria": "Vitória",
        "Volta Rerdonda": "Volta Redonda",
        "Mesquita": "São João de Meriti",
        "Santana do Parnaiba": "Santana de Parnaíba",
    },
    "Canada": {
        "Edmaonton": "Edmonton",
        "Edmonton / St. Albert": "St. Albert",
        "Edmonton / Spruce Grove": "Spruce Grove",
        "Ednomton": "Edmonton",
        "Gibbons / Edmonton": "Edmonton",
        "Hull": "Gatineau",
        "Jonquiere": "Saguenay",
        "Jonquière": "Saguenay",
        "Levis": "Lévis",
        "Marie Ville": "Montréal",
        "Marieville": "Montréal",
        "Montral": "Montréal",
        "Montreal": "Montréal",
        "Niagara": "Niagara Falls",
        "Qubec City": "Québec",
        "Qubec": "Québec",
        "Quebec": "Québec",
        "Scarborough": "Toronto",
        "St. Albert / Edmonton": "St. Albert",
        "St Catharines": "Sainte-Catherine (Monteregie)",
        "St Catherines": "Sainte-Catherine (Monteregie)",
        "St. Catherines": "Sainte-Catherine (Monteregie)",
        "St-Eustache": "Saint-Eustache",
        "St Eustache": "Saint-Eustache",
        "St. Hubert": "Longueuil",
        "Saint-Hubert": "Longueuil",
        "St-Jean-sur-Richelieu": "Saint-Jean-sur-Richelieu",
        "St-Jerome": "Saint-Jérôme",
        "St-Lazare": "Saint-Lazare",
        "Sudbury": "Greater Sudbury",
        "Sault St. Marie": "Sault Ste. Marie",
        "Sault Sainte Marie": "Sault Ste. Marie",
        "Longueil": "Longueuil",
        "Mtl": "Montréal",
        "Fort Saskatchewan": "Edmonton",
        "Beauport": "Québec",
        "Sainte-Foy": "Québec",
        "Chicoutimi": "Saguenay",
    },
    "Chile": {
        "Concepcin": "Concepción",
        "Concepcion": "Concepción",
        "Entre Juegos, Santiago": "Santiago",
        "Magic Sur, Santiago": "Santiago",
        "Maip": "Santiago",
        "Quilpue": "Quilpué",
        "Santiago de Chile": "Santiago",
        "Santiago (primogénito)": "Santiago",
        "TableCat Games / Rancagua": "Rancagua",
        "Valparaiso": "Valparaíso",
        "Vina del Mar": "Viña del Mar",
    },
    "Colombia": {"Bogata": "Bogotá", "Bogota": "Bogotá", "Medellin": "Medellín"},
    "Czech Republic": {
        "Brmo": "Brno",
        "Hradec Kralove": "Hradec Králové",
        "Hradec Krlov": "Hradec Králové",
        "Nachod": "Náchod",
        "Plzen": "Pilsen",
        "Praha": "Prague",
        "Slany": "Slaný",
        "Trutnov, Mal Svatoovice": "Trutnov",
        "Vsetin": "Vsetín",
        "Zlin": "Zlín",
        "Frýdek - Místek": "Frýdek-Místek",
        "Esk Budjovice": "České Budějovice",
    },
    "Denmark": {"Aarhus": "Århus", "Arhus": "Århus", "Rhus": "Århus"},
    "Finland": {
        "Hyvinkää": "Hyvinge",
        "Kauniainen": "Espoo",
        "Kuusankoski": "Kouvola",
        "Tikkurila": "Vantaa",
    },
    "France": {
        "Alès ": "Alès",
        "Alès / Aix en provence": "Alès",
        "Saint Dizier": "Saint-Dizier",
        "Saint DIizer": "Saint-Dizier",
        "Oye Plage": "Calais",
        "Oye-Plage": "Calais",
        "Gravelines": "Dunkerque",
        "Savigny le Temple": "Melun",
        "Juvisy": "Paris",
        "Bures-sur-Yvette": "Paris",
        "Cévennes": "Nîmes",
    },
    "Germany": {
        "Cologne": "Köln",
        "Dsseldorf": "Düsseldorf",
        "Duesseldorf": "Düsseldorf",
        "Frankfurt": "Frankfurt am Main",
        "Gttingen": "Göttingen",
        "Hanau": "Frankfurt am Main",
        "Ludwigshafen": "Ludwigshafen am Rhein",
        "Madgeburg": "Magdeburg",
        "Marburg": "Marburg an der Lahn",
        "Moerfelden": "Mörfelden-Walldorf",
        "Seeheim": "Darmstadt",
        "Sttutgart": "Stuttgart",
        "Stuttgart / Ludwigsburg": "Ludwigsburg",
        "Ramstein": "Kaiserslautern",
        "Schwalbach": "Frankfurt am Main",
        "Mhltal": "Darmstadt",
        "Kaufungen": "Kassel",
        "Egelsbach": "Darmstadt",
        "Erzhausen": "Darmstadt",
        "Huerth": "Köln",
        "Troisdorf": "Bonn",
        "Mnster": "Münster",
        "Karlesruhe": "Karlsruhe",
        "Dren": "Düren",
    },
    "Greece": {
        "Athens, Attica": "Athens",
        "Athnes": "Athens",
        "Chania": "Chaniá",
        "Thessaloniki": "Thessaloníki",
        "Thessaoniki": "Thessaloníki",
    },
    "Hungary": {
        "debrecen": "Debrecen",
        "Debrechen": "Debrecen",
        "Erdőkertes": "Budapest",
        "Godollo": "Gödöllő",
        "Kaposvar": "Kaposvár",
        "Kecskemet": "Kecskemét",
        "Kismaros": "Budapest",
        "Nyiregyhaza": "Nyíregyháza",
        "Pecs": "Pécs",
        "Salgotarjan": "Salgótarján",
        "Salgtarjn": "Salgótarján",
        "Szekesfehervar": "Székesfehérvár",
        "Szkesfehrvr": "Székesfehérvár",
        "Trnok": "Budapest",
        "Veszprem": "Veszprém",
        "Veszprm": "Veszprém",
        "Pest": "Budapest",
        "Kekcskemét": "Kecskemét",
        "Kistarcsa": "Budapest",
        "Tãrnok": "Budapest",
    },
    "Iceland": {
        "Reykjavik": "Reykjavík",
        "Reykjaví­k": "Reykjavík",
        "Reyjavik": "Reykjavík",
    },
    "Israel": {"Bat-Yam": "Bat Yam", "Tel-Aviv": "Tel Aviv"},
    "Italy": {
        "Firenze": "Florence",
        "Reggio Emilia": "Reggio nell'Emilia",
        "Torino": "Turin",
        "Milano": "Milan",
        "Genova": "Genoa",
        "Grugliasco (Torino)": "Turin",
        "FIrenze": "Florence",
        "Tuscany": "Florence",
        "Val di Susa": "Turin",
        "Massa Carrara": "Massa",
    },
    "Japan": {"Anjo": "Anjō", "Sendai": "Sendai (Miyagi)", "Kanagawa": "Yokohama"},
    "Mexico": {
        "Ciudad de México ": "Mexico City",
        "Ciudad de México": "Mexico City",
        "Distrito Federal": "Mexico City",
        "Durango": "Victoria de Durango",
        "Durango, Durango": "Victoria de Durango",
        "Guadalajara, jalisco": "Guadalajara",
        "Monterey, N.L.": "Monterrey",
        "Naucalpan": "Naucalpan de Juárez",
        "Neza": "Ciudad Nezahualcoyotl",
        "Nezahualcoyotl": "Ciudad Nezahualcoyotl",
        "Nezahualcóyotl": "Ciudad Nezahualcoyotl",
        "Puebla": "Puebla (Puebla)",
        "Puebla de Zaragoza": "Puebla (Puebla)",
        "Queretaro": "Santiago de Querétaro",
        "Toluca de Lerdo": "Toluca",
        "Toluca De Lerdo": "Toluca",
        "Leon": "León de los Aldama",
        "Netzahualcoyotl": "Ciudad Nezahualcoyotl",
        "Estado de México": "Toluca",
    },
    "Netherlands": {
        "Houten": "Utrecht",
        "Krommenie": "Zaanstad",
        "Rotterdan": "Rotterdam",
        "S-Hertogenbosch": "'s-Hertogenbosch",
        "s-Hertogenbosch": "'s-Hertogenbosch",
        "Almere": "Almere Stad",
        "Haag": "The Hague",
    },
    "New Zealand": {
        "WELLINGTON": "Wellington",
        "Plamerston North": "Palmerston North",
        "Wellingon": "Wellington",
    },
    "Norway": {"Fjellhamar": "Oslo"},
    "Panama": {"Panama": "Panamá"},
    "Philippines": {
        "Bacolod": "Bacolod City",
        "Caloocan": "Caloocan City",
        "Dasmarinas, Cavite": "Dasmariñas",
        "Las Pias": "Las Piñas",
        "Los Banos": "Los Baños",
        "Los Baos": "Los Baños",
        "Makati": "Makati City",
        "Marikina": "Marikina City",
        "Metro Manila": "Manila",
        "Parañaque City": "Paranaque City",
        "Quezon": "Quezon City",
        "Quezon city": "Quezon City",
        "Quezon City, Metro Manila": "Quezon City",
        "Taguig City": "Taguig",
        "Tondo, Manila": "Manila",
        "Pasig": "Pasig City",
        "Pasay City": "Pasay",
        "Pasay city": "Pasay",
        "Calamba City": "Calamba",
        "Las Piñas City": "Las Piñas",
        "Muntinlupa City": "Manila",
        "Laguna": "Calamba",
    },
    "Poland": {
        "Aleksandrow Lodzki": "Aleksandrów Łódzki",
        "Andrespol": "Łódź",
        "Bedzin": "Będzin",
        "Bialystok": "Białystok",
        "Białstok": "Białystok",
        "Bielsko Biaa": "Bielsko-Biala",
        "Bielsko Biała": "Bielsko-Biala",
        "Bielsko-Biała": "Bielsko-Biala",
        "Bielsko-Biaa": "Bielsko-Biala",
        "Boleawiec": "Bolesławiec",
        "Bolesawiec": "Bolesławiec",
        "Cracow": "Kraków",
        "Cracov": "Kraków",
        "Czstochowa": "Częstochowa",
        "Czestochowa": "Częstochowa",
        "Hajnowka": "Hajnówka",
        "Jelenia Gora": "Jelenia Góra",
        "Kędzierzyn Koźle": "Kędzierzyn-Koźle",
        "Krakw": "Kraków",
        "Krakow": "Kraków",
        "Kraszew": "Łódź",
        "Lodz": "Łódź",
        "Lubon": "Luboń",
        "Nowa Sol": "Nowa Sól",
        "Poznan": "Poznań",
        "Swidnik": "Świdnik",
        "Szczezin": "Szczecin",
        "Toru": "Toruń",
        "Torun": "Toruń",
        "Wroclaw": "Wrocław",
        "Warszawa": "Warsaw",
        "Gdask": "Gdańsk",
        "Górnicza": "Dąbrowa Górnicza",
    },
    "Portugal": {
        "Lisboa": "Lisbon",
        "Setubal": "Setúbal",
        "Setbal": "Setúbal",
        "Agualva-Cacém": "Cacém",
        "Sacavm": "Lisbon",
        "Rinchoa": "Lisbon",
        "Seixal": "Lisbon",
    },
    "Russian Federation": {
        "Moskow": "Moscow",
        "Saint-Petersburg": "Saint Petersburg",
        "St. Peterburg": "Saint Petersburg",
    },
    "Slovakia": {
        "Banska Bystrica": "Banská Bystrica",
        "Kosice": "Košice",
    },
    "Spain": {
        "Barberá del Vallés": "Barberà del Vallès",
        "Barcellona": "Barcelona",
        "Barcelona ": "Barcelona",
        "Cádiz": "Cadiz",
        "Castellón de la Plana": "Castelló de la Plana",
        "Castellón": "Castelló de la Plana",
        "Córdoba ": "Córdoba",
        "Gerona": "Girona",
        "Hospitalet de Llobregat": "L'Hospitalet de Llobregat",
        "La Coruña": "A Coruña",
        "Las Palmas": "Las Palmas de Gran Canaria",
        "Las Palmas de Gran Canarias": "Las Palmas de Gran Canaria",
        "Lucena (Córdoba)": "Lucena",
        "Madirid": "Madrid",
        "Masnou": "El Masnou",
        "Mollet del Vallés": "Mollet del Vallès",
        "Palma de Mallorca": "Palma",
        "Rentería": "Errenteria",
        "San Pedro de Alcántara": "Marbella",
        "San Sebastián": "San Sebastián de los Reyes",
        "Sant Cugat del Vallés": "Sant Cugat del Vallès",
        "Sant Quirze del Vallés": "Sant Quirze del Vallès",
        "Santa Coloma de Gramanet": "Santa Coloma de Gramenet",
        "Sóller": "Palma",
        "Villafranca de Córdoba": "Córdoba",
        "Vitoria": "Gasteiz / Vitoria",
        "Vitoria-Gasteiz": "Gasteiz / Vitoria",
        "Fernán Núñez": "Córdoba",
        "La Corredoría": "Oviedo",
        "Pola de Siero": "Oviedo",
        "Badía del Vallés": "Sabadell",
        "La Llagosta": "Mollet del Vallès",
        "Las Rozas": "Las Rozas de Madrid",
    },
    "South Africa": {"Johanneburg": "Johannesburg", "Kempton Park": "Johannesburg"},
    "Sweden": {
        "Malmo": "Malmö",
        "Örnsköldsviks": "Örnsköldsvik",
        "Stockholm ": "Stockholm",
        "Gothenburg": "Göteborg",
    },
    "Switzerland": {"Geneva": "Genève", "Zurich": "Zürich"},
    "Ukraine": {"Kiev": "Kyiv"},
    "United States": {
        "ABQ": "Albuquerque",
        "Albuqueruqe": "Albuquerque",
        "Cincinnatti": "Cincinnati",
        "Cinncinati": "Cincinnati",
        "denver": "Denver",
        "Indanapolis": "Indianapolis",
        "Las vegas": "Las Vegas",
        "Los Angelas": "Los Angeles",
        "Los Angleles": "Los Angeles",
        "Mililani": "Mililani Town",
        "New York": "New York City",
        "NYC": "New York City",
        "Palm Bay, FL": "Palm Bay",
        "San Fransisco": "San Francisco",
        "St. George": "Saint George",
        "St Louis": "St. Louis",
        "St. Paul": "Saint Paul",
        "St Paul": "Saint Paul",
        "Saint peters": "Saint Peters",
        "Washington": "Washington (District of Columbia)",
        "Washington, D.C.": "Washington (District of Columbia)",
        "Bronx": "New York City",
        "Winston Salem": "Winston-Salem",
        "Tuscon": "Tucson",
        "Minnepolis": "Minneapolis",
        "SLC": "Salt Lake City",
        "Virgina Beach": "Virginia Beach",
        "Kalmazoo": "Kalamazoo",
        "Binghaamton": "Binghamton",
        "Grands Forks": "Grand Forks",
        "Virginia": "Richmond (Virginia)",
        "Texas": "Austin (Texas)",
    },
    "United Kingdom": {
        "Burton-On-Trent": "Burton upon Trent",
        "Burton-on-Trent": "Burton upon Trent",
        "Burton-on-trent": "Burton upon Trent",
        "Burton-onTrent": "Burton upon Trent",
        "Burton on Trent": "Burton upon Trent",
        "Ealing": "London",
        "Flint, Wales": "Liverpool",
        "Kings Lynn": "King's Lynn",
        "Milton keynes": "Milton Keynes",
        "Newcastle": "Newcastle upon Tyne",
        "Newcastle-Upon-Tyne": "Newcastle upon Tyne",
        "Newcastle Upon-Tyne": "Newcastle upon Tyne",
        "Newcastle Upon Tyne": "Newcastle upon Tyne",
        "Newcastle upon tyne": "Newcastle upon Tyne",
        "Newport, South Wales": "Newport (Wales)",
        "Northhampton": "Northampton",
        "Notttingham": "Nottingham",
        "Rochester, Kent": "Rochester",
        "Shefield": "Sheffield",
        "St. Albans": "St Albans",
        "St. Andrews": "Saint Andrews",
        "St. Helens": "St Helens",
        "St. Neots": "Saint Neots",
        "Hull": "Kingston upon Hull",
        "Southend": "Southend-on-Sea",
        "West Midlands": "Birmingham",
        "Merseyside": "Liverpool",
        "Yorkshire": "York",
        "Worcestershire": "Worcester",
        "Buckinghamshire": "Aylesbury",
    },
}


class VEKNSyncService:
    def __init__(self) -> None:
        self.client = VEKNAPIClient()

    async def close(self) -> None:
        await self.client.close()

    def _map_vekn_to_user(self, vekn_player: dict[str, Any]) -> dict[str, Any]:
        name = f"{vekn_player.get('firstname', '')} {vekn_player.get('lastname', '')}".strip()
        vekn_id = str(vekn_player.get("veknid", ""))

        city = vekn_player.get("city") or None
        country_name = vekn_player.get("countryname") or ""
        country_code = vekn_player.get("countrycode") or ""
        if city and country_name in FIX_CITIES:
            city = FIX_CITIES[country_name].get(city, city)
        city_geoname_id = None
        if city and country_code:
            matched = match_city(city, country_code)
            if matched:
                city = matched["name"]
                city_geoname_id = matched["geoname_id"]
            else:
                city = None

        # Roles seeded once by _derive_role_seeds on create, never touched here.
        vekn_prefix = None
        if vekn_player.get("princeid"):
            vekn_prefix = str(vekn_player.get("princeid"))
        elif vekn_player.get("coordinatorid"):
            vekn_prefix = str(vekn_player.get("coordinatorid"))

        fields: dict[str, Any] = {
            "name": name or "Unknown",
            "country": vekn_player.get("countrycode") or None,
            "vekn_id": vekn_id,
            "city": city,
            "city_geoname_id": city_geoname_id,
            "state": vekn_player.get("statename") or None,
            "vekn_prefix": vekn_prefix,
        }
        # Set only when present in the scraped list, so non-officials' emails and
        # any self-edited address (guarded by local_modifications) stay untouched.
        official_email = OFFICIALS_EMAILS.get(vekn_id)
        if official_email:
            fields["contact_email"] = official_email
        return fields

    async def _get_user_by_vekn_id(self, vekn_id: str) -> User | None:
        async with get_connection() as conn:
            # Live rows only: the archon merge tombstones vekn-created duplicates,
            # so matching a dead one here would update a dead copy, not the survivor.
            result = await conn.execute(
                """
                SELECT "full"
                FROM objects
                WHERE type = %s AND "full"->>'vekn_id' = %s
                  AND deleted_at IS NULL
                LIMIT 1
                """,
                (ObjectType.USER, vekn_id),
            )
            row = await result.fetchone()
            if not row:
                return None

            return decode_json(row[0], User)

    async def _create_user(self, vekn_data: dict[str, Any]) -> User:
        now = datetime.now(UTC)
        user = User(
            uid=str(uuid7()),
            modified=now,
            vekn_synced=True,
            vekn_synced_at=now,
            **vekn_data,
        )

        bd = await save_user(user)
        broadcast_precomputed(bd)
        return user

    async def _update_user(
        self, existing_user: User, vekn_data: dict[str, Any]
    ) -> tuple[User, bool]:
        """Applies only actually-changed fields, skipping the write (and its SSE
        broadcast) when nothing changed."""
        changed = {
            field: value
            for field, value in vekn_data.items()
            if field not in existing_user.local_modifications
            and getattr(existing_user, field) != value
        }
        if not changed:
            return existing_user, False

        now = datetime.now(UTC)
        for field, value in changed.items():
            setattr(existing_user, field, value)
        existing_user.vekn_synced = True
        existing_user.vekn_synced_at = now
        existing_user.modified = now

        bd = await save_user(existing_user)
        broadcast_precomputed(bd)

        return existing_user, True

    async def sync_player(self, vekn_player: dict[str, Any]) -> tuple[User, str]:
        """Returns (User, action) where action is "created", "updated" or "unchanged"."""
        vekn_data = self._map_vekn_to_user(vekn_player)
        vekn_id = vekn_data.get("vekn_id")

        if not vekn_id:
            raise ValueError("VEKN player data missing veknid")

        existing_user = await self._get_user_by_vekn_id(vekn_id)

        if existing_user:
            user, changed = await self._update_user(existing_user, vekn_data)
            return user, "updated" if changed else "unchanged"
        else:
            vekn_data["roles"] = _derive_role_seeds(vekn_player)
            return await self._create_user(vekn_data), "created"

    async def sync_all_members(self) -> dict[str, int]:
        logger.info("Starting VEKN member sync")
        stats = {"created": 0, "updated": 0, "unchanged": 0, "errors": 0, "total": 0}

        try:
            players = await self.client.fetch_all_members()
            stats["total"] = len(players)

            for player in players:
                try:
                    _, action = await self.sync_player(player)
                    stats[action] += 1
                except Exception as e:
                    logger.error(f"Error syncing player {player}: {e}")
                    stats["errors"] += 1

            logger.info(
                f"VEKN sync completed: {stats['created']} created, "
                f"{stats['updated']} updated, {stats['unchanged']} unchanged, "
                f"{stats['errors']} errors, {stats['total']} total"
            )

            inferred_prefix = await self._infer_coopted_by()
            inferred_city = await self._infer_coopted_by_city()
            logger.info(
                f"Inferred coopted_by: {inferred_prefix} prefix, {inferred_city} city/country"
            )

        except VEKNAPIError as e:
            logger.error(f"VEKN API error during sync: {e}")
            raise

        return stats

    async def _infer_coopted_by(self) -> int:
        """Prefix-matches VEKN IDs against a Prince/NC's vekn_prefix; sets
        coopted_by only when unset."""
        sponsors = await get_users_with_vekn_prefix()
        if not sponsors:
            return 0

        count = 0
        now = datetime.now(UTC)

        for sponsor in sponsors:
            if not sponsor.vekn_prefix:
                continue

            sponsored_users = await get_users_by_vekn_prefix(sponsor.vekn_prefix)

            for user in sponsored_users:
                if user.uid == sponsor.uid:
                    continue
                if user.coopted_by:
                    continue

                # Mutate in place — a from-scratch User(...) would drop new fields.
                user.coopted_by = sponsor.uid
                user.coopted_at = None
                user.modified = now
                bd = await save_user(user)
                broadcast_precomputed(bd)
                count += 1

        return count

    async def _infer_coopted_by_city(self) -> int:
        """Two-phase fallback: city-level Prince match, then country-level NC
        match. Skips ambiguous cases (multiple candidates for one city/country)."""
        sponsors = await get_users_with_vekn_prefix()
        orphans = await get_users_without_coopted_by()
        if not sponsors or not orphans:
            return 0

        prince_by_city: dict[tuple[str, str], str] = {}  # (country, city) -> uid
        ambiguous_cities: set[tuple[str, str]] = set()
        nc_by_country: dict[str, str] = {}  # country -> uid
        ambiguous_countries: set[str] = set()

        for s in sponsors:
            if Role.PRINCE in s.roles and s.city and s.country:
                key = (s.country, s.city)
                if key in ambiguous_cities:
                    continue
                if key in prince_by_city:
                    ambiguous_cities.add(key)
                    del prince_by_city[key]
                else:
                    prince_by_city[key] = s.uid

            if Role.NC in s.roles and s.country:
                if s.country in ambiguous_countries:
                    continue
                if s.country in nc_by_country:
                    ambiguous_countries.add(s.country)
                    del nc_by_country[s.country]
                else:
                    nc_by_country[s.country] = s.uid

        count = 0
        now = datetime.now(UTC)
        still_orphan: list[User] = []

        for user in orphans:
            if user.city and user.country:
                sponsor_uid = prince_by_city.get((user.country, user.city))
                if sponsor_uid and sponsor_uid != user.uid:
                    user.coopted_by = sponsor_uid
                    user.modified = now
                    bd = await save_user(user)
                    broadcast_precomputed(bd)
                    count += 1
                    continue
            still_orphan.append(user)

        for user in still_orphan:
            if user.country:
                sponsor_uid = nc_by_country.get(user.country)
                if sponsor_uid and sponsor_uid != user.uid:
                    user.coopted_by = sponsor_uid
                    user.modified = now
                    bd = await save_user(user)
                    broadcast_precomputed(bd)
                    count += 1

        return count
