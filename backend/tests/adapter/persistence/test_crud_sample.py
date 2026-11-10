from sqlalchemy.orm import Session

from backend.common.db import begin_transaction
from backend.domain.models.project import Project
from backend.domain.models.sample import ProjectSample
from backend.adapter.persistence import crud_project
from backend.adapter.persistence import crud_sample


def _make_project_with_samples(db: Session, n: int = 3):
    with begin_transaction(db):
        project = crud_project.create(
            db=db,
            project=Project(
                name="n", description="d", tips="t", created_by=1, updated_by=1
            ),
        )
    samples = [
        ProjectSample(
            project_id=project.id,
            created_by=1,
            updated_by=1,
            data="{}",
            annotated_count=i,
        )
        for i in range(n)
    ]
    with begin_transaction(db):
        crud_sample.batch(db=db, samples=samples)
    return project


class TestCrudSampleSortInjection:
    """Regression tests for SQL injection via the sample-listing sort param."""

    def test_error_based_injection_is_ignored(self, db: Session):
        project = _make_project_with_samples(db)
        # a non-existent column injected after a valid pair must NOT reach SQL
        sorting = "updated_at:asc,SQLI_MARKER_no_such_col:asc"
        results = crud_sample.list_by(
            db=db,
            project_id=project.id,
            after=None,
            before=None,
            page=0,
            size=10,
            sorting=sorting,
        )
        assert len(results) == 3

    def test_boolean_based_injection_has_no_effect(self, db: Session):
        project = _make_project_with_samples(db)
        payload_true = (
            "state:asc,(CASE WHEN 1=1 THEN project_sample.id "
            "ELSE 0-project_sample.id END):desc"
        )
        payload_false = (
            "state:asc,(CASE WHEN 1=0 THEN project_sample.id "
            "ELSE 0-project_sample.id END):desc"
        )
        ids_true = [
            s.id
            for s in crud_sample.list_by(
                db=db,
                project_id=project.id,
                after=None,
                before=None,
                page=0,
                size=10,
                sorting=payload_true,
            )
        ]
        ids_false = [
            s.id
            for s in crud_sample.list_by(
                db=db,
                project_id=project.id,
                after=None,
                before=None,
                page=0,
                size=10,
                sorting=payload_false,
            )
        ]
        # if the injected CASE executed, the two orderings would differ
        assert ids_true == ids_false

    def test_valid_sort_still_works(self, db: Session):
        project = _make_project_with_samples(db)
        results = crud_sample.list_by(
            db=db,
            project_id=project.id,
            after=None,
            before=None,
            page=0,
            size=10,
            sorting="annotated_count:desc",
        )
        counts = [s.annotated_count for s in results]
        assert counts == sorted(counts, reverse=True)

    def test_state_sort_still_works(self, db: Session):
        project = _make_project_with_samples(db)
        results = crud_sample.list_by(
            db=db,
            project_id=project.id,
            after=None,
            before=None,
            page=0,
            size=10,
            sorting="state:asc",
        )
        assert len(results) == 3
