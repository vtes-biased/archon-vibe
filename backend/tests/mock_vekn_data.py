"""Generate mock VEKN data for testing."""

import random
from datetime import UTC, datetime, timedelta

from src.models import Role, User


def generate_mock_users(count: int = 400) -> list[User]:
    """Generate realistic mock VEKN users for testing.
    
    Args:
        count: Number of users to generate (default 400 for pagination testing)
    
    Returns:
        List of User objects with varied data
    """
    first_names = [
        "John", "Jane", "Michael", "Sarah", "David", "Emma", "Robert", "Lisa",
        "William", "Mary", "James", "Patricia", "Thomas", "Jennifer", "Charles",
        "Linda", "Daniel", "Elizabeth", "Matthew", "Barbara", "Anthony", "Susan",
        "Mark", "Jessica", "Donald", "Karen", "Paul", "Nancy", "Steven", "Betty",
        "Andrew", "Margaret", "Kenneth", "Sandra", "Joshua", "Ashley", "Kevin",
        "Kimberly", "Brian", "Emily", "George", "Donna", "Timothy", "Michelle",
        "Ronald", "Carol", "Edward", "Amanda", "Jason", "Melissa", "Jeffrey",
        "Deborah", "Ryan", "Stephanie", "Jacob", "Rebecca", "Gary", "Sharon",
        "Nicholas", "Laura", "Eric", "Cynthia", "Jonathan", "Kathleen", "Stephen",
        "Amy", "Larry", "Angela", "Justin", "Shirley", "Scott", "Anna", "Brandon",
        "Brenda", "Benjamin", "Pamela", "Samuel", "Emma", "Raymond", "Nicole",
        "Gregory", "Helen", "Alexander", "Samantha", "Patrick", "Katherine",
    ]
    
    last_names = [
        "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
        "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
        "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
        "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
        "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
        "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green",
        "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
        "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz",
        "Parker", "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris",
        "Morales", "Murphy", "Cook", "Rogers", "Gutierrez", "Ortiz", "Morgan",
        "Cooper", "Peterson", "Bailey", "Reed", "Kelly", "Howard", "Ramos",
        "Kim", "Cox", "Ward", "Richardson", "Watson", "Brooks", "Chavez",
        "Wood", "James", "Bennett", "Gray", "Mendoza", "Ruiz", "Hughes",
    ]
    
    countries = [
        "US", "CA", "GB", "DE", "FR", "ES", "IT", "AU", "NZ", "JP",
        "BR", "MX", "AR", "CL", "NL", "BE", "SE", "NO", "DK", "FI",
        "PL", "CZ", "AT", "CH", "PT", "IE", "IL", "SG", "HK", "TW",
    ]
    
    cities = {
        "US": ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia"],
        "CA": ["Toronto", "Montreal", "Vancouver", "Calgary", "Ottawa", "Edmonton"],
        "GB": ["London", "Manchester", "Birmingham", "Leeds", "Glasgow", "Liverpool"],
        "DE": ["Berlin", "Hamburg", "Munich", "Cologne", "Frankfurt", "Stuttgart"],
        "FR": ["Paris", "Marseille", "Lyon", "Toulouse", "Nice", "Nantes"],
        "ES": ["Madrid", "Barcelona", "Valencia", "Seville", "Zaragoza", "Malaga"],
        "IT": ["Rome", "Milan", "Naples", "Turin", "Palermo", "Genoa"],
        "AU": ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Canberra"],
        "NZ": ["Auckland", "Wellington", "Christchurch", "Hamilton", "Dunedin"],
        "BR": ["São Paulo", "Rio de Janeiro", "Brasília", "Salvador", "Fortaleza"],
    }
    
    all_roles = [Role.IC, Role.NC, Role.PRINCE, Role.ETHICS, Role.PTC, Role.PT, Role.RULEMONGER, Role.JUDGE]
    
    users = []
    base_time = datetime.now(UTC)
    
    for i in range(count):
        first_name = random.choice(first_names)
        last_name = random.choice(last_names)
        name = f"{first_name} {last_name}"
        
        country = random.choice(countries)
        city = random.choice(cities.get(country, ["Unknown"])) if random.random() > 0.3 else None
        
        # Generate VEKN ID (format: some have it, some don't)
        vekn_id = f"{random.randint(1000000, 9999999)}" if random.random() > 0.2 else None
        
        # Some users have nicknames
        nickname = f"{first_name[:3]}{random.randint(10, 99)}" if random.random() > 0.7 else None
        
        # Assign roles - most users have 0-2 roles
        role_count = random.choices([0, 1, 2, 3], weights=[60, 25, 10, 5])[0]
        user_roles = random.sample(all_roles, min(role_count, len(all_roles))) if role_count > 0 else []
        
        # Modified time varies
        modified = base_time - timedelta(days=random.randint(0, 365))
        
        # Some users are VEKN synced
        vekn_synced = random.random() > 0.3
        vekn_synced_at = modified if vekn_synced else None
        
        # Generate proper UUID v7 format
        from uuid6 import uuid7
        user = User(
            uid=str(uuid7()),
            modified=modified,
            name=name,
            country=country,
            vekn_id=vekn_id,
            city=city,
            state=None,  # Keep simple for now
            nickname=nickname,
            roles=user_roles,
            vekn_synced=vekn_synced,
            vekn_synced_at=vekn_synced_at,
            local_modifications=set(),
        )
        users.append(user)
    
    return users

