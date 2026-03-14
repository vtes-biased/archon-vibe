"""VEKN member synchronization service."""

import logging
from datetime import UTC, datetime
from typing import Any

from uuid6 import uuid7

from .db import (
    decode_json,
    get_connection,
    get_princes_and_ncs,
    get_users_by_vekn_prefix,
    get_users_without_coopted_by,
    insert_user,
    update_user,
)
from .geonames import match_city
from .models import ObjectType, Role, User
from .vekn_api import VEKNAPIClient, VEKNAPIError

logger = logging.getLogger(__name__)

# Static role assignments (maintained outside VEKN API)
ADMINS: set[str] = {
    "3200340",
    "3200188",
    "8180022",
    "3190007",
    "2050001",
    "1002480",
}

JUDGES: dict[str, Role] = {
    "8180022": Role.RULEMONGER,
    "3200188": Role.RULEMONGER,
    "3190007": Role.JUDGE,
    "4200005": Role.RULEMONGER,
    "8530107": Role.JUDGE,
    "2340000": Role.JUDGE,
    "6260014": Role.JUDGE,
    "1940030": Role.JUDGE,
    "1003731": Role.JUDGE,
    "1003455": Role.RULEMONGER,
    "3200340": Role.RULEMONGER,
    "1003030": Role.JUDGE,
    "3070069": Role.JUDGE,
    "4960027": Role.JUDGE,
    "2810001": Role.JUDGE,
    "3190133": Role.JUDGE,
    "3190041": Role.JUDGE,
    "8030009": Role.JUDGE,
    "9510021": Role.JUDGE,
    "3370036": Role.JUDGE,
    "1000629": Role.JUDGE,
    "1002855": Role.JUDGEKIN,
    "3340152": Role.JUDGEKIN,
    "5360022": Role.JUDGE,
    "8390001": Role.JUDGEKIN,
    "3070006": Role.JUDGEKIN,
    "4960046": Role.JUDGEKIN,
    "6140001": Role.JUDGEKIN,
    "3020044": Role.JUDGEKIN,
    "3020010": Role.JUDGEKIN,
    "1003584": Role.JUDGEKIN,
    "1003214": Role.JUDGEKIN,
    "4110004": Role.JUDGEKIN,
    "4110113": Role.JUDGEKIN,
    "4100033": Role.JUDGEKIN,
    "2331000": Role.JUDGEKIN,
    "3680057": Role.JUDGEKIN,
    "4100008": Role.JUDGEKIN,
    "3120101": Role.JUDGEKIN,
    "4960000": Role.JUDGEKIN,
    "3010501": Role.JUDGEKIN,
    "6060022": Role.JUDGEKIN,
    "5540005": Role.JUDGEKIN,
    "3530067": Role.JUDGE,
}

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
    """Service for syncing VEKN members with local database."""

    def __init__(self) -> None:
        """Initialize sync service."""
        self.client = VEKNAPIClient()

    async def close(self) -> None:
        """Close the VEKN API client."""
        await self.client.close()

    def _map_vekn_to_user(self, vekn_player: dict[str, Any]) -> dict[str, Any]:
        """
        Map VEKN API player data to User model fields.

        Args:
            vekn_player: Player data from VEKN API

        Returns:
            Dictionary of User fields
        """
        # Combine first and last name
        name = f"{vekn_player.get('firstname', '')} {vekn_player.get('lastname', '')}".strip()
        vekn_id = str(vekn_player.get("veknid", ""))

        # Fix city name and validate against geonames
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

        # Infer Prince/NC roles from princeid/coordinatorid presence
        roles: list[Role] = []
        if vekn_player.get("princeid"):
            roles.append(Role.PRINCE)
        if vekn_player.get("coordinatorid"):
            roles.append(Role.NC)

        # Add static role assignments
        if vekn_id in ADMINS:
            roles.append(Role.IC)
        if vekn_id in JUDGES:
            roles.append(JUDGES[vekn_id])

        # Extract vekn_prefix for Prince/NC users
        vekn_prefix = None
        if vekn_player.get("princeid"):
            vekn_prefix = str(vekn_player.get("princeid"))
        elif vekn_player.get("coordinatorid"):
            vekn_prefix = str(vekn_player.get("coordinatorid"))

        return {
            "name": name or "Unknown",
            "country": vekn_player.get("countrycode") or None,
            "vekn_id": vekn_id,
            "city": city,
            "city_geoname_id": city_geoname_id,
            "state": vekn_player.get("statename") or None,
            "roles": roles,
            "vekn_prefix": vekn_prefix,
        }

    async def _get_user_by_vekn_id(self, vekn_id: str) -> User | None:
        """
        Get user by VEKN ID.

        Args:
            vekn_id: VEKN ID to search for

        Returns:
            User if found, None otherwise
        """
        async with get_connection() as conn:
            result = await conn.execute(
                """
                SELECT "full"
                FROM objects
                WHERE type = %s AND "full"->>'vekn_id' = %s
                LIMIT 1
                """,
                (ObjectType.USER, vekn_id),
            )
            row = await result.fetchone()
            if not row:
                return None

            return decode_json(row[0], User)

    async def _create_user(self, vekn_data: dict[str, Any]) -> User:
        """
        Create new user from VEKN data.

        Args:
            vekn_data: Mapped VEKN player data

        Returns:
            Created User
        """
        now = datetime.now(UTC)
        user = User(
            uid=str(uuid7()),
            modified=now,
            vekn_synced=True,
            vekn_synced_at=now,
            **vekn_data,
        )

        await insert_user(user)
        return user

    async def _update_user(
        self, existing_user: User, vekn_data: dict[str, Any]
    ) -> tuple[User, bool]:
        """
        Update existing user with VEKN data, preserving local modifications.

        Only updates the database if actual data changed, to avoid triggering
        the modified timestamp update and unnecessary frontend sync.

        Args:
            existing_user: Existing user
            vekn_data: Mapped VEKN player data

        Returns:
            Tuple of (User, changed) where changed indicates if data was modified
        """
        # Build update dict, excluding locally modified fields
        update_fields = {}
        for field, value in vekn_data.items():
            if field not in existing_user.local_modifications:
                update_fields[field] = value

        # Check if any data actually changed
        new_name = update_fields.get("name", existing_user.name)
        new_country = update_fields.get("country", existing_user.country)
        new_city = update_fields.get("city", existing_user.city)
        new_city_geoname_id = update_fields.get("city_geoname_id", existing_user.city_geoname_id)
        new_state = update_fields.get("state", existing_user.state)
        new_roles = update_fields.get("roles", existing_user.roles)
        new_vekn_prefix = update_fields.get("vekn_prefix", existing_user.vekn_prefix)

        has_changes = (
            new_name != existing_user.name
            or new_country != existing_user.country
            or new_city != existing_user.city
            or new_city_geoname_id != existing_user.city_geoname_id
            or new_state != existing_user.state
            or sorted(new_roles) != sorted(existing_user.roles)
            or new_vekn_prefix != existing_user.vekn_prefix
        )

        # Skip DB update if no changes (preserves original modified timestamp)
        if not has_changes:
            return existing_user, False

        # Apply changes to existing user, preserving all non-sync fields
        now = datetime.now(UTC)
        existing_user.name = new_name
        existing_user.country = new_country
        existing_user.city = new_city
        existing_user.city_geoname_id = new_city_geoname_id
        existing_user.state = new_state
        existing_user.roles = new_roles
        existing_user.vekn_prefix = new_vekn_prefix
        existing_user.vekn_synced = True
        existing_user.vekn_synced_at = now
        existing_user.modified = now

        await update_user(existing_user)
        return existing_user, True

    async def sync_player(self, vekn_player: dict[str, Any]) -> tuple[User, str]:
        """
        Sync a single player from VEKN API.

        Args:
            vekn_player: Player data from VEKN API

        Returns:
            Tuple of (User, action) where action is "created", "updated", or "unchanged"
        """
        vekn_data = self._map_vekn_to_user(vekn_player)
        vekn_id = vekn_data.get("vekn_id")

        if not vekn_id:
            raise ValueError("VEKN player data missing veknid")

        # Check if user exists
        existing_user = await self._get_user_by_vekn_id(vekn_id)

        if existing_user:
            user, changed = await self._update_user(existing_user, vekn_data)
            return user, "updated" if changed else "unchanged"
        else:
            return await self._create_user(vekn_data), "created"

    async def sync_all_members(self) -> dict[str, int]:
        """
        Sync all VEKN members.

        Returns:
            Dictionary with sync statistics
        """
        logger.info("Starting VEKN member sync")
        stats = {"created": 0, "updated": 0, "unchanged": 0, "errors": 0, "total": 0}

        try:
            # Fetch all members from VEKN API
            players = await self.client.fetch_all_members()
            stats["total"] = len(players)

            # Sync each player
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

            # Infer coopted_by relationships
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
        """Infer coopted_by relationships from VEKN ID prefix matching.

        For each Prince/NC with a vekn_prefix, find users whose VEKN ID
        starts with that prefix and set coopted_by if not already set.

        Returns the number of users updated.
        """
        sponsors = await get_princes_and_ncs()
        if not sponsors:
            return 0

        count = 0
        now = datetime.now(UTC)

        for sponsor in sponsors:
            if not sponsor.vekn_prefix:
                continue

            # Find users whose VEKN ID starts with this sponsor's prefix
            sponsored_users = await get_users_by_vekn_prefix(sponsor.vekn_prefix)

            for user in sponsored_users:
                # Skip if user is the sponsor themselves
                if user.uid == sponsor.uid:
                    continue
                # Skip if coopted_by already set
                if user.coopted_by:
                    continue

                # Update user with coopted_by
                updated = User(
                    uid=user.uid,
                    modified=now,
                    name=user.name,
                    country=user.country,
                    vekn_id=user.vekn_id,
                    city=user.city,
                    state=user.state,
                    nickname=user.nickname,
                    roles=user.roles,
                    avatar_path=user.avatar_path,
                    contact_email=user.contact_email,
                    contact_discord=user.contact_discord,
                    contact_phone=user.contact_phone,
                    coopted_by=sponsor.uid,
                    coopted_at=None,  # Historical - no timestamp
                    vekn_synced=user.vekn_synced,
                    vekn_synced_at=user.vekn_synced_at,
                    local_modifications=user.local_modifications,
                    vekn_prefix=user.vekn_prefix,
                )
                await update_user(updated)
                count += 1

        return count

    async def _infer_coopted_by_city(self) -> int:
        """Infer coopted_by from city (Prince) then country (NC) fallback.

        Phase 1: Match users to Princes in the same city.
        Phase 2: Match remaining users to NCs in the same country.
        Skips ambiguous cases (multiple Princes in same city, multiple NCs in same country).

        Returns the number of users updated.
        """
        sponsors = await get_princes_and_ncs()
        orphans = await get_users_without_coopted_by()
        if not sponsors or not orphans:
            return 0

        # Build lookups
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

        # Phase 1: Prince by city
        for user in orphans:
            if user.city and user.country:
                sponsor_uid = prince_by_city.get((user.country, user.city))
                if sponsor_uid and sponsor_uid != user.uid:
                    user.coopted_by = sponsor_uid
                    user.modified = now
                    await update_user(user)
                    count += 1
                    continue
            still_orphan.append(user)

        # Phase 2: NC by country
        for user in still_orphan:
            if user.country:
                sponsor_uid = nc_by_country.get(user.country)
                if sponsor_uid and sponsor_uid != user.uid:
                    user.coopted_by = sponsor_uid
                    user.modified = now
                    await update_user(user)
                    count += 1

        return count
