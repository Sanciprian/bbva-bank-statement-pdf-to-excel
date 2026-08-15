from bank_parser.models.document import SpatialDocument
from bank_parser.profiles.base import BankProfile
from bank_parser.profiles.bbva import BBVA_PROFILE
from bank_parser.profiles.generic import GENERIC_PROFILE

KNOWN_PROFILES: list[BankProfile] = [BBVA_PROFILE]


def select_profile(document: SpatialDocument, profiles: list[BankProfile] = KNOWN_PROFILES) -> BankProfile:
    for profile in profiles:
        if profile.matches(document):
            return profile
    return GENERIC_PROFILE
