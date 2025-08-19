from sqlalchemy import and_, exists
from sqlalchemy.orm import Query, Session

from aixcc.db import (
    BugGroup,
    Patch,
    PatchBug,
    PatchStatus,
)


def search_available_patch_query(session: Session, bug_profile_id: int) -> Query[Patch]:
    """
    Returns a query for available patches for a given bug profile.
    A patch is considered available if the following conditions are met:

    1. The patch is associated with the given bug profile.
    2. The patch has no failing functionality tests.
    3. The patch is not associated with any bugs that are not repaired in the bug group of the bug profile.

    """

    return (
        session.query(Patch)
        .filter(Patch.bug_profile_id == bug_profile_id)
        .filter(
            ~exists().where(
                and_(
                    PatchStatus.patch_id == Patch.id,
                    PatchStatus.functionality_tests_passing == False,
                )
            )
        )
        .filter(
            ~exists().where(
                and_(
                    PatchBug.patch_id == Patch.id,
                    PatchBug.bug_id.in_(
                        session.query(BugGroup.bug_id).filter(
                            BugGroup.bug_profile_id == bug_profile_id,
                        ),
                    ),
                    PatchBug.repaired == False,
                )
            )
        )
    )
