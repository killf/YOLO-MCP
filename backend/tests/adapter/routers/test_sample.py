import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from backend.common.config import settings
from backend.common.db import begin_transaction
from backend.adapter.persistence import crud_user
from backend.adapter.persistence import crud_project
from backend.adapter.persistence import crud_sample
from backend.domain.models.project import Project
from backend.domain.models.sample import ProjectSample
from backend.domain.models.attachment import ProjectAttachment


@pytest.mark.parametrize("state", ["SKIPPED", "NEW", "DONE"])
def test_state_only_patch_preserves_annotation(
    client, testuser_token_headers, training_project, state
):
    """切换状态不能抹掉已保存标注及数量，重新完成时校验原有结果。"""
    base = f"/api/v1/projects/{training_project}/samples"
    before = client.get(
        base, headers=testuser_token_headers, params={"page": 0}
    ).json()["data"][0]
    response = client.patch(
        f"{base}/{before['id']}",
        headers=testuser_token_headers,
        json={"state": state},
    )
    assert response.status_code == 200
    after = response.json()["data"]
    assert after["state"] == state
    assert after["data"] == before["data"]
    assert after["annotated_count"] == before["annotated_count"] == 1


def test_count_only_patch_preserves_annotation(
    client, testuser_token_headers, training_project
):
    base = f"/api/v1/projects/{training_project}/samples"
    before = client.get(
        base, headers=testuser_token_headers, params={"page": 0}
    ).json()["data"][0]
    response = client.patch(
        f"{base}/{before['id']}",
        headers=testuser_token_headers,
        json={"annotated_count": 2},
    )
    assert response.status_code == 200
    assert response.json()["data"]["data"] == before["data"]
    assert response.json()["data"]["annotated_count"] == 2


@pytest.mark.parametrize("data", [None, {}, {"result": {}}, {"result": "broken"}])
def test_invalid_completed_annotation_does_not_overwrite_saved_data(
    client, testuser_token_headers, training_project, data
):
    base = f"/api/v1/projects/{training_project}/samples"
    before = client.get(
        base, headers=testuser_token_headers, params={"page": 0}
    ).json()["data"][0]
    response = client.patch(
        f"{base}/{before['id']}",
        headers=testuser_token_headers,
        json={"state": "DONE", "data": data},
    )
    assert response.status_code == 422
    after = client.get(f"{base}/{before['id']}", headers=testuser_token_headers).json()[
        "data"
    ]
    assert after["data"] == before["data"]
    assert after["annotated_count"] == before["annotated_count"]


class TestClassProjectSampleRouter:
    def test_split_filter_pagination_and_global_stats(
        self, client: TestClient, testuser_token_headers: dict, db: Session
    ) -> None:
        """划分筛选在分页前生效，统计排除删除样本且保持项目全量范围。"""
        owner = crud_user.get_user_by_username(db=db, username="test@example.com")
        with begin_transaction(db):
            project = crud_project.create(
                db=db,
                project=Project(name="split", created_by=owner.id, updated_by=owner.id),
            )
            other = crud_project.create(
                db=db,
                project=Project(name="other", created_by=owner.id, updated_by=owner.id),
            )
            samples = crud_sample.batch(
                db=db,
                samples=[
                    ProjectSample(
                        project_id=project.id,
                        created_by=owner.id,
                        updated_by=owner.id,
                        split=split,
                        state=state,
                        data="{}",
                    )
                    for split, state in [
                        ("train", "DONE"),
                        ("test", "DONE"),
                        ("train", "NEW"),
                        ("test", "SKIPPED"),
                    ]
                ],
            )
            crud_sample.delete(db=db, sample_ids=[samples[-1].id])
            crud_sample.batch(
                db=db,
                samples=[
                    ProjectSample(
                        project_id=other.id,
                        data="{}",
                        split="test",
                        created_by=owner.id,
                        updated_by=owner.id,
                    )
                ],
            )

        url = f"{settings.API_V1_STR}/projects/{project.id}"
        for split, ids in [
            ("train", [samples[0].id, samples[2].id]),
            ("test", [samples[1].id]),
        ]:
            for page, sample_id in enumerate(ids):
                response = client.get(
                    f"{url}/samples",
                    headers=testuser_token_headers,
                    params={"split": split, "page": page, "size": 1},
                )
                assert response.status_code == 200
                assert [row["id"] for row in response.json()["data"]] == [sample_id]
                assert response.json()["meta_data"]["total"] == len(ids)

        all_samples = client.get(
            f"{url}/samples",
            headers=testuser_token_headers,
            params={"page": 0},
        )
        assert all_samples.json()["meta_data"]["total"] == 3
        for filters, ids in [
            ({"state": "DONE"}, [samples[0].id, samples[1].id]),
            ({"state": "NEW"}, [samples[2].id]),
            ({"state": "SKIPPED"}, []),
            ({"state": "DONE", "split": "test"}, [samples[1].id]),
            ({"state": "NEW", "split": "test"}, []),
        ]:
            response = client.get(
                f"{url}/samples",
                headers=testuser_token_headers,
                params={"page": 0, **filters},
            )
            assert response.status_code == 200
            assert [item["id"] for item in response.json()["data"]] == ids
            assert response.json()["meta_data"]["total"] == len(ids)
        response = client.get(
            f"{url}/samples",
            headers=testuser_token_headers,
            params={"after": samples[0].id, "state": "DONE"},
        )
        assert [item["id"] for item in response.json()["data"]] == [samples[1].id]
        assert (
            client.get(
                f"{url}/samples",
                headers=testuser_token_headers,
                params={"page": 0, "state": "invalid"},
            ).status_code
            == 422
        )
        invalid = client.get(
            f"{url}/samples",
            headers=testuser_token_headers,
            params={"page": 0, "split": "validation"},
        )
        assert invalid.status_code == 422
        expected = {"new": 1, "done": 2, "skipped": 0, "train": 2, "test": 1}
        detail = client.get(url, headers=testuser_token_headers)
        assert detail.json()["data"]["stats"] == expected
        listing = client.get(
            f"{settings.API_V1_STR}/projects",
            headers=testuser_token_headers,
            params={"page": 0, "size": 10},
        )
        listed_project = next(
            p for p in listing.json()["data"] if p["id"] == project.id
        )
        assert listed_project["stats"] == expected

    def test_create_sample_successful(
        self, client: TestClient, testuser_token_headers: dict, db: Session
    ) -> None:

        # prepare data
        current_user = crud_user.get_user_by_username(
            db=db, username="test@example.com"
        )
        with begin_transaction(db):
            project = crud_project.create(
                db=db,
                project=Project(
                    name="name",
                    description="description",
                    tips="tips",
                    created_by=current_user.id,
                    updated_by=current_user.id,
                ),
            )
        with begin_transaction(db):
            file = ProjectAttachment(
                project_id=project.id,
                path=f"projects/{project.id}/images/a.png",
                filename="a.png",
                created_by=current_user.id,
                updated_by=current_user.id,
            )
            db.add(file)
            db.flush()
        data = [{"file_id": file.id, "data": {}}]

        # run
        r = client.post(
            f"{settings.API_V1_STR}/projects/{project.id}/samples",
            headers=testuser_token_headers,
            json=data,
        )

        # check
        db.expire_all()
        updated_project = crud_project.get(db=db, project_id=project.id)
        json = r.json()
        assert r.status_code == 201
        assert len(json["data"]["ids"]) == 1
        assert updated_project.status == "IMPORTED"

    def test_create_sample_project_status_not_draft(
        self, client: TestClient, testuser_token_headers: dict, db: Session
    ) -> None:

        # prepare data
        current_user = crud_user.get_user_by_username(
            db=db, username="test@example.com"
        )
        with begin_transaction(db):
            project = crud_project.create(
                db=db,
                project=Project(
                    name="name",
                    description="description",
                    tips="tips",
                    created_by=current_user.id,
                    updated_by=current_user.id,
                    status="CONFIGURED",
                ),
            )
        with begin_transaction(db):
            file = ProjectAttachment(
                project_id=project.id,
                path=f"projects/{project.id}/images/a.png",
                filename="a.png",
                created_by=current_user.id,
                updated_by=current_user.id,
            )
            db.add(file)
            db.flush()
        data = [{"file_id": file.id, "data": {}}]

        # run
        r = client.post(
            f"{settings.API_V1_STR}/projects/{project.id}/samples",
            headers=testuser_token_headers,
            json=data,
        )

        # check
        db.expire_all()
        updated_project = crud_project.get(db=db, project_id=project.id)
        json = r.json()
        assert r.status_code == 201
        assert len(json["data"]["ids"]) == 1
        assert updated_project.status == "CONFIGURED"

    def test_create_sample_project_not_found(
        self, client: TestClient, testuser_token_headers: dict, db: Session
    ) -> None:

        # prepare data
        data = [{"file_id": 1, "data": {}}]

        # run
        r = client.post(
            f"{settings.API_V1_STR}/projects/0/samples",
            headers=testuser_token_headers,
            json=data,
        )

        # check
        json = r.json()
        assert r.status_code == 404
        assert json["err_code"] == 50002

    def test_sample_list_by_page(
        self, client: TestClient, testuser_token_headers: dict, db: Session
    ) -> None:

        # prepare data
        current_user = crud_user.get_user_by_username(
            db=db, username="test@example.com"
        )
        with begin_transaction(db):
            project = crud_project.create(
                db=db,
                project=Project(
                    name="name",
                    description="description",
                    tips="tips",
                    created_by=current_user.id,
                    updated_by=current_user.id,
                ),
            )
        samples = [
            ProjectSample(
                project_id=project.id,
                created_by=current_user.id,
                updated_by=current_user.id,
                data="{}",
            )
            for i in range(14)
        ]
        with begin_transaction(db):
            crud_sample.batch(
                db=db,
                samples=samples,
            )

        # run
        r = client.get(
            f"{settings.API_V1_STR}/projects/{project.id}/samples",
            headers=testuser_token_headers,
            params={"page": 0, "size": 10},
        )

        # check
        json = r.json()
        assert r.status_code == 200
        assert len(json["data"]) == 10
        assert json["data"][0]["id"] == 1
        assert json["meta_data"]["total"] == 14

    def test_sample_list_by_before(
        self, client: TestClient, testuser_token_headers: dict, db: Session
    ) -> None:

        # prepare data
        current_user = crud_user.get_user_by_username(
            db=db, username="test@example.com"
        )
        with begin_transaction(db):
            project = crud_project.create(
                db=db,
                project=Project(
                    name="name",
                    description="description",
                    tips="tips",
                    created_by=current_user.id,
                    updated_by=current_user.id,
                ),
            )
        samples = [
            ProjectSample(
                project_id=project.id,
                created_by=current_user.id,
                updated_by=current_user.id,
                data="{}",
            )
            for i in range(14)
        ]
        with begin_transaction(db):
            crud_sample.batch(
                db=db,
                samples=samples,
            )

        # run
        r = client.get(
            f"{settings.API_V1_STR}/projects/{project.id}/samples",
            headers=testuser_token_headers,
            params={"before": 13, "size": 10},
        )

        # check
        json = r.json()
        assert r.status_code == 200
        assert len(json["data"]) == 10
        assert json["data"][0]["id"] == 3
        assert json["data"][-1]["id"] == 12
        assert json["meta_data"]["total"] == 14

    def test_sample_list_by_after(
        self, client: TestClient, testuser_token_headers: dict, db: Session
    ) -> None:

        # prepare data
        current_user = crud_user.get_user_by_username(
            db=db, username="test@example.com"
        )
        with begin_transaction(db):
            project = crud_project.create(
                db=db,
                project=Project(
                    name="name",
                    description="description",
                    tips="tips",
                    created_by=current_user.id,
                    updated_by=current_user.id,
                ),
            )
        samples = [
            ProjectSample(
                project_id=project.id,
                created_by=current_user.id,
                updated_by=current_user.id,
                data="{}",
            )
            for i in range(14)
        ]
        with begin_transaction(db):
            crud_sample.batch(
                db=db,
                samples=samples,
            )

        # run
        r = client.get(
            f"{settings.API_V1_STR}/projects/{project.id}/samples",
            headers=testuser_token_headers,
            params={"after": 5, "size": 10},
        )

        # check
        json = r.json()
        assert r.status_code == 200
        assert len(json["data"]) == 9
        assert json["data"][0]["id"] == 6
        assert json["data"][8]["id"] == 14
        assert json["meta_data"]["total"] == 14

    def test_sample_list_with_sort(
        self, client: TestClient, testuser_token_headers: dict, db: Session
    ) -> None:

        # prepare data
        current_user = crud_user.get_user_by_username(
            db=db, username="test@example.com"
        )
        with begin_transaction(db):
            project = crud_project.create(
                db=db,
                project=Project(
                    name="name",
                    description="description",
                    tips="tips",
                    created_by=current_user.id,
                    updated_by=current_user.id,
                ),
            )
        samples = [
            ProjectSample(
                project_id=project.id,
                created_by=current_user.id,
                updated_by=current_user.id,
                data="{}",
                annotated_count=i,
            )
            for i in range(14)
        ]
        with begin_transaction(db):
            crud_sample.batch(
                db=db,
                samples=samples,
            )

        # get actual sample IDs for assertions
        sample_ids = sorted([s.id for s in samples])
        after_id = sample_ids[4]  # 5th sample (index 4)

        # run
        r = client.get(
            f"{settings.API_V1_STR}/projects/{project.id}/samples",
            headers=testuser_token_headers,
            params={"sort": "annotated_count:desc", "after": after_id, "size": 10},
        )

        # check
        json = r.json()
        assert r.status_code == 200
        assert len(json["data"]) == 9
        # first item should have highest annotated_count (sorted desc)
        assert json["data"][0]["annotated_count"] >= json["data"][1]["annotated_count"]
        assert json["meta_data"]["total"] == 14

    def test_sample_list_by_params_error(
        self, client: TestClient, testuser_token_headers: dict, db: Session
    ) -> None:

        # prepare data

        # run
        r = client.get(
            f"{settings.API_V1_STR}/projects/{1}/samples",
            headers=testuser_token_headers,
            params={"after": 1, "before": 1, "page": 1, "size": 10},
        )

        # check
        assert r.status_code == 422

    def test_sample_list_by_sort_error(
        self, client: TestClient, testuser_token_headers: dict, db: Session
    ) -> None:

        # prepare data
        current_user = crud_user.get_user_by_username(
            db=db, username="test@example.com"
        )
        with begin_transaction(db):
            project = crud_project.create(
                db=db,
                project=Project(
                    name="name",
                    description="description",
                    tips="tips",
                    created_by=current_user.id,
                    updated_by=current_user.id,
                ),
            )
        # run
        r = client.get(
            f"{settings.API_V1_STR}/projects/{project.id}/samples",
            headers=testuser_token_headers,
            params={"sort": "", "page": 0, "size": 10},
        )

        # check
        assert r.status_code == 422

    def test_batch_auto_label_forbidden_for_non_owner(
        self,
        client: TestClient,
        testuser_token_headers: dict,
        db: Session,
        other_user_id,
        monkeypatch,
    ) -> None:
        # enable the AI feature so the request reaches the access check
        monkeypatch.setattr(settings, "USE_AUTO_LABEL", True)
        # project owned by another user
        with begin_transaction(db):
            project = crud_project.create(
                db=db,
                project=Project(
                    name="other",
                    description="d",
                    tips="t",
                    media_type="IMAGE",
                    created_by=other_user_id,
                    updated_by=other_user_id,
                ),
            )
        r = client.post(
            f"{settings.API_V1_STR}/projects/{project.id}/auto_label_job",
            headers=testuser_token_headers,
        )
        assert r.status_code == 403

    def test_collaborator_can_annotate_shared_project(
        self,
        client: TestClient,
        testuser_token_headers: dict,
        db: Session,
        admin_token_headers,
    ) -> None:
        # owner = the default test user
        owner = crud_user.get_user_by_username(db=db, username="test@example.com")

        # a second user, added as collaborator, with a real login token
        collab_username = "collab_annotator@example.com"
        client.post(
            f"{settings.API_V1_STR}/users",
            headers=admin_token_headers,
            json={"username": collab_username, "password": "collab@123"},
        )
        login = client.post(
            f"{settings.API_V1_STR}/users/login",
            json={"username": collab_username, "password": "collab@123"},
        )
        collab_headers = {"Authorization": login.json()["data"]["token"]}
        collab_user = crud_user.get_user_by_username(db=db, username=collab_username)

        with begin_transaction(db):
            project = crud_project.create(
                db=db,
                project=Project(
                    name="shared",
                    description="d",
                    tips="t",
                    created_by=owner.id,
                    updated_by=owner.id,
                ),
            )
        with begin_transaction(db):
            samples = crud_sample.batch(
                db=db,
                samples=[
                    ProjectSample(
                        project_id=project.id,
                        created_by=owner.id,
                        updated_by=owner.id,
                        data="{}",
                    )
                ],
            )
        sid = samples[0].id

        # owner adds the collaborator
        r = client.post(
            f"{settings.API_V1_STR}/projects/{project.id}/collaborators",
            headers=testuser_token_headers,
            json={"user_id": collab_user.id},
        )
        assert r.status_code == 201

        # the collaborator can list, read and annotate samples in the shared project
        r = client.get(
            f"{settings.API_V1_STR}/projects/{project.id}/samples",
            headers=collab_headers,
            params={"page": 0, "size": 10},
        )
        assert r.status_code == 200
        r = client.get(
            f"{settings.API_V1_STR}/projects/{project.id}/samples/{sid}",
            headers=collab_headers,
        )
        assert r.status_code == 200
        r = client.patch(
            f"{settings.API_V1_STR}/projects/{project.id}/samples/{sid}",
            headers=collab_headers,
            json={"data": {"k": "v"}, "annotated_count": 1},
        )
        assert r.status_code == 200

    def test_sample_access_forbidden_for_non_member(
        self,
        client: TestClient,
        testuser_token_headers: dict,
        db: Session,
        other_user_id,
    ) -> None:
        # 项目属于其他用户，当前用户既非拥有者也非协作者。
        with begin_transaction(db):
            project = crud_project.create(
                db=db,
                project=Project(
                    name="other",
                    description="d",
                    tips="t",
                    created_by=other_user_id,
                    updated_by=other_user_id,
                ),
            )
        with begin_transaction(db):
            samples = crud_sample.batch(
                db=db,
                samples=[
                    ProjectSample(
                        project_id=project.id,
                        created_by=other_user_id,
                        updated_by=other_user_id,
                        data="{}",
                    )
                ],
            )
        sid = samples[0].id

        # list
        r = client.get(
            f"{settings.API_V1_STR}/projects/{project.id}/samples",
            headers=testuser_token_headers,
            params={"page": 0, "size": 10},
        )
        assert r.status_code == 403
        # get
        r = client.get(
            f"{settings.API_V1_STR}/projects/{project.id}/samples/{sid}",
            headers=testuser_token_headers,
        )
        assert r.status_code == 403
        # patch
        r = client.patch(
            f"{settings.API_V1_STR}/projects/{project.id}/samples/{sid}",
            headers=testuser_token_headers,
            json={"data": {}, "annotated_count": 0},
        )
        assert r.status_code == 403
        # delete
        r = client.request(
            "delete",
            f"{settings.API_V1_STR}/projects/{project.id}/samples",
            headers=testuser_token_headers,
            json={"sample_ids": [sid]},
        )
        assert r.status_code == 403

    def test_sample_get(
        self, client: TestClient, testuser_token_headers: dict, db: Session
    ) -> None:

        # prepare data
        current_user = crud_user.get_user_by_username(
            db=db, username="test@example.com"
        )
        with begin_transaction(db):
            project = crud_project.create(
                db=db,
                project=Project(
                    name="name",
                    description="description",
                    tips="tips",
                    created_by=current_user.id,
                    updated_by=current_user.id,
                ),
            )
        with begin_transaction(db):
            samples = crud_sample.batch(
                db=db,
                samples=[
                    ProjectSample(
                        project_id=project.id,
                        created_by=current_user.id,
                        updated_by=current_user.id,
                        data="{}",
                    )
                ],
            )

        print(samples)

        # run
        r = client.get(
            f"{settings.API_V1_STR}/projects/{project.id}/samples/{samples[0].id}",
            headers=testuser_token_headers,
        )

        # check
        assert r.status_code == 200
        assert r.json()["data"]["id"] == samples[0].id

    def test_sample_get_not_found(
        self, client: TestClient, testuser_token_headers: dict, db: Session
    ) -> None:

        # prepare data
        current_user = crud_user.get_user_by_username(
            db=db, username="test@example.com"
        )
        with begin_transaction(db):
            project = crud_project.create(
                db=db,
                project=Project(
                    name="name",
                    description="description",
                    tips="tips",
                    created_by=current_user.id,
                    updated_by=current_user.id,
                ),
            )

        # run
        r = client.get(
            f"{settings.API_V1_STR}/projects/{project.id}/samples/0",
            headers=testuser_token_headers,
        )

        # check
        json = r.json()
        assert r.status_code == 404
        assert json["err_code"] == 55001

    def test_sample_patch(
        self, client: TestClient, testuser_token_headers: dict, db: Session
    ) -> None:

        # prepare data
        current_user = crud_user.get_user_by_username(
            db=db, username="test@example.com"
        )
        with begin_transaction(db):
            project = crud_project.create(
                db=db,
                project=Project(
                    name="name",
                    description="description",
                    tips="tips",
                    created_by=current_user.id,
                    updated_by=current_user.id,
                ),
            )
        with begin_transaction(db):
            samples = crud_sample.batch(
                db=db,
                samples=[
                    ProjectSample(
                        project_id=project.id,
                        created_by=current_user.id,
                        updated_by=current_user.id,
                        data="{}",
                    )
                ],
            )

        # run
        data = {
            "data": {"key1": "value1", "key2": [{"key3": "value3"}]},
            "annotated_count": 1,
        }
        r = client.patch(
            f"{settings.API_V1_STR}/projects/{project.id}/samples/{samples[0].id}",
            headers=testuser_token_headers,
            json=data,
        )

        # check
        json = r.json()
        assert r.status_code == 200
        assert json["data"]["state"] == "DONE"

    def test_sample_patch_skip(
        self, client: TestClient, testuser_token_headers: dict, db: Session
    ) -> None:

        # prepare data
        current_user = crud_user.get_user_by_username(
            db=db, username="test@example.com"
        )
        with begin_transaction(db):
            project = crud_project.create(
                db=db,
                project=Project(
                    name="name",
                    description="description",
                    tips="tips",
                    created_by=current_user.id,
                    updated_by=current_user.id,
                ),
            )
        with begin_transaction(db):
            samples = crud_sample.batch(
                db=db,
                samples=[
                    ProjectSample(
                        project_id=project.id,
                        created_by=current_user.id,
                        updated_by=current_user.id,
                        data="{}",
                    )
                ],
            )

        # run
        data = {"state": "SKIPPED"}
        r = client.patch(
            f"{settings.API_V1_STR}/projects/{project.id}/samples/{samples[0].id}",
            headers=testuser_token_headers,
            json=data,
        )

        # check
        json = r.json()
        assert r.status_code == 200
        assert json["data"]["state"] == "SKIPPED"

    def test_sample_patch_project_not_found(
        self, client: TestClient, testuser_token_headers: dict, db: Session
    ) -> None:

        # prepare data

        # run
        data = {"state": "SKIPPED"}
        r = client.patch(
            f"{settings.API_V1_STR}/projects/0/samples/0",
            headers=testuser_token_headers,
            json=data,
        )
        # check
        json = r.json()
        assert r.status_code == 404
        assert json["err_code"] == 50002

    def test_sample_patch_project_sample_not_found(
        self, client: TestClient, testuser_token_headers: dict, db: Session
    ) -> None:

        # prepare data
        current_user = crud_user.get_user_by_username(
            db=db, username="test@example.com"
        )
        with begin_transaction(db):
            project = crud_project.create(
                db=db,
                project=Project(
                    name="name",
                    description="description",
                    tips="tips",
                    created_by=current_user.id,
                    updated_by=current_user.id,
                ),
            )

        # run
        data = {"state": "SKIPPED"}
        r = client.patch(
            f"{settings.API_V1_STR}/projects/{project.id}/samples/0",
            headers=testuser_token_headers,
            json=data,
        )
        # check
        json = r.json()
        assert r.status_code == 404
        assert json["err_code"] == 55001

    def test_sample_delete(
        self, client: TestClient, testuser_token_headers: dict, db: Session
    ) -> None:

        # prepare data
        current_user = crud_user.get_user_by_username(
            db=db, username="test@example.com"
        )
        with begin_transaction(db):
            project = crud_project.create(
                db=db,
                project=Project(
                    name="name",
                    description="description",
                    tips="tips",
                    created_by=current_user.id,
                    updated_by=current_user.id,
                ),
            )
        with begin_transaction(db):
            samples = crud_sample.batch(
                db=db,
                samples=[
                    ProjectSample(
                        project_id=project.id,
                        created_by=current_user.id,
                        updated_by=current_user.id,
                        data="{}",
                    )
                ],
            )

        # run
        data = {"sample_ids": [samples[0].id]}
        r = client.request(
            "delete",
            f"{settings.API_V1_STR}/projects/{project.id}/samples",
            headers=testuser_token_headers,
            json=data,
        )

        # check
        assert r.status_code == 200

    def test_sample_delete_not_found(
        self, client: TestClient, testuser_token_headers: dict, db: Session
    ) -> None:

        # prepare data
        current_user = crud_user.get_user_by_username(
            db=db, username="test@example.com"
        )
        with begin_transaction(db):
            project = crud_project.create(
                db=db,
                project=Project(
                    name="name",
                    description="description",
                    tips="tips",
                    created_by=current_user.id,
                    updated_by=current_user.id,
                ),
            )

        # run
        data = {"sample_ids": [1, 2]}
        r = client.request(
            "delete",
            f"{settings.API_V1_STR}/projects/{project.id}/samples",
            headers=testuser_token_headers,
            json=data,
        )

        # check
        assert r.status_code == 200
