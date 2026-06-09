"""Security properties of join-code generation (CWE-330).

Community and household join codes act as bearer tokens — anyone who knows a
code can join — so they must come from a CSPRNG, not the seedable `random`
module. These tests assert format and CSPRNG independence from random.seed().
"""

import random
import re

from apps.communities.models import generate_join_code
from apps.households.models import generate_household_code


class TestJoinCodeGeneration:
    def test_community_code_format(self):
        code = generate_join_code()
        assert re.fullmatch(r"[A-Z0-9]{8}", code)

    def test_household_code_format(self):
        code = generate_household_code()
        assert re.fullmatch(r"H-[A-Z0-9]{6}", code)

    def test_community_code_uses_csprng_not_seedable_random(self):
        """Seeding the `random` module must not make codes predictable."""
        random.seed(0)
        first = generate_join_code()
        random.seed(0)
        second = generate_join_code()
        assert first != second

    def test_household_code_uses_csprng_not_seedable_random(self):
        random.seed(0)
        first = generate_household_code()
        random.seed(0)
        second = generate_household_code()
        assert first != second

    def test_codes_are_unique_in_bulk(self):
        codes = {generate_join_code() for _ in range(2000)}
        assert len(codes) == 2000
