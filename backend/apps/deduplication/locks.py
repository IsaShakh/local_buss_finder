from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import sha256
from uuid import UUID

from django.db import connection

# ASCII "LBI1", fixed for every entity-resolution/decision caller.
OWNER_RESOLUTION_NAMESPACE = 0x4C424931


@contextmanager
def owner_resolution_lock(owner_id: UUID | int) -> Iterator[None]:
    """Serialize an owner's entity changes until the outer transaction ends."""
    assert connection.in_atomic_block, "Owner resolution requires an active transaction."
    # The current AUTH_USER_MODEL has integer IDs; UUID owners use the same
    # stable textual encoding so callers never depend on Python's hash seed.
    owner_key = int.from_bytes(
        sha256(str(owner_id).encode("ascii")).digest()[:4], "big", signed=True
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s, %s)",
            [OWNER_RESOLUTION_NAMESPACE, owner_key],
        )
    yield
