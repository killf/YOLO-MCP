"""创建 YOLO MCP 2.0.0 的完整初始表结构、索引和外键。"""

from alembic import op
import sqlalchemy as sa

# 本脚本仅用于初始化空库，不修改已有数据库结构。
revision = "e5f6a7b8c9d0"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """在空数据库中建立完整业务结构，不读取应用模型或历史数据。"""
    # 1. 创建账户表及其索引。
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=50), nullable=True),
        sa.Column("hashed_password", sa.String(length=255), nullable=True),
        sa.Column("is_admin", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("auth_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Time the user was created",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last time the user was updated",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_username"), "user", ["username"], unique=True)

    op.create_table(
        "access_token",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_access_token_user_id", "access_token", ["user_id"])

    # 2. 创建项目与数据集配置表及其索引。
    op.create_table(
        "project",
        sa.Column("ai_algorithm", sa.String(32), nullable=False, server_default="yolo"),
        sa.Column(
            "training_config",
            sa.JSON(),
            nullable=True,
            comment="开始训练时使用的默认参数",
        ),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=True),
        sa.Column(
            "description",
            sa.String(length=1024),
            nullable=True,
            comment="project description",
        ),
        sa.Column(
            "tips", sa.String(length=1024), nullable=True, comment="project tips"
        ),
        sa.Column(
            "ai_model_name",
            sa.String(length=1024),
            nullable=True,
            comment="自动标注的权重文件名或官方模型 ID",
        ),
        sa.Column(
            "last_sample_inner_id",
            sa.Integer(),
            nullable=True,
            comment="The last inner id of sample in a project",
        ),
        sa.Column("config", sa.Text(), nullable=True, comment="project config yaml"),
        sa.Column(
            "media_type",
            sa.String(length=32),
            nullable=True,
            comment="project media type: image, video, audio",
        ),
        sa.Column(
            "status", sa.String(length=32), nullable=True, comment="project status"
        ),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "updated_by",
            sa.Integer(),
            nullable=True,
            comment="Last time a project was updated by",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Time a project was created",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last time a project was updated",
        ),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Project delete time",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["user.id"],
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_project_id_deleted_at_index", "project", ["id", "deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_project_created_by"), "project", ["created_by"], unique=False
    )
    op.create_index(
        op.f("ix_project_deleted_at"), "project", ["deleted_at"], unique=False
    )
    op.create_index(op.f("ix_project_name"), "project", ["name"], unique=False)

    # 3. 创建 AI 预标注批次表及其索引。
    op.create_table(
        "auto_label_job",
        sa.Column("algorithm", sa.String(32), nullable=False, server_default="yolo"),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=True),
        sa.Column("processed_count", sa.Integer(), nullable=True),
        sa.Column("success_count", sa.Integer(), nullable=True),
        sa.Column("failed_count", sa.Integer(), nullable=True),
        sa.Column(
            "model_name",
            sa.String(length=1024),
            server_default="",
            nullable=False,
            comment="本批次使用的权重文件名或模型 ID",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["user.id"],
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_auto_label_job_project_id"),
        "auto_label_job",
        ["project_id"],
        unique=False,
    )

    # 4. 创建图片与附件引用表及其索引。
    op.create_table(
        "project_attachment",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "filename", sa.String(length=256), nullable=True, comment="file name"
        ),
        sa.Column(
            "path",
            sa.String(length=256),
            nullable=True,
            comment="项目目录下的文件相对路径",
        ),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Time a project was created",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last time a project was updated",
        ),
        sa.Column(
            "deleted_at", sa.DateTime(), nullable=True, comment="Project delete time"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["user.id"],
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_attachment_id_deleted_at",
        "project_attachment",
        ["id", "deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_attachment_created_by"),
        "project_attachment",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_attachment_deleted_at"),
        "project_attachment",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_attachment_project_id"),
        "project_attachment",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_attachment_updated_by"),
        "project_attachment",
        ["updated_by"],
        unique=False,
    )

    # 5. 创建项目协作者表及其索引。
    op.create_table(
        "project_collaborator",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Time a project collaborator was created",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "user_id"),
    )
    op.create_index(
        op.f("ix_project_collaborator_project_id"),
        "project_collaborator",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_collaborator_user_id"),
        "project_collaborator",
        ["user_id"],
        unique=False,
    )

    # 6. 创建样本预标注表及其索引。
    op.create_table(
        "project_pre_annotation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True, comment="Project ID"),
        sa.Column(
            "sample_name",
            sa.String(length=255),
            nullable=True,
            comment="One of the sample names of the project",
        ),
        sa.Column("file_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Time a project sample result was created",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last time a project pre annotation result was updated",
        ),
        sa.Column(
            "data",
            sa.Text(),
            nullable=True,
            comment="project sample pre annotation result",
        ),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Project pre-annotation delete time",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["user.id"],
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["project_attachment.id"],
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_pre_annotation_id_deleted_at",
        "project_pre_annotation",
        ["id", "deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_pre_annotation_created_by"),
        "project_pre_annotation",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_pre_annotation_deleted_at"),
        "project_pre_annotation",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_pre_annotation_file_id"),
        "project_pre_annotation",
        ["file_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_pre_annotation_sample_name"),
        "project_pre_annotation",
        ["sample_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_pre_annotation_project_id"),
        "project_pre_annotation",
        ["project_id"],
        unique=False,
    )

    # 7. 创建样本与数据集划分表及其索引。
    op.create_table(
        "project_sample",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "inner_id", sa.Integer(), nullable=True, comment="sample id in a project"
        ),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("file_id", sa.Integer(), nullable=True),
        sa.Column(
            "split",
            sa.String(length=16),
            server_default="train",
            nullable=False,
            comment="训练集或测试集",
        ),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Time a project sample result was created",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last time a project sample result was updated",
        ),
        sa.Column(
            "annotated_count",
            sa.Integer(),
            nullable=True,
            comment="project sample result count",
        ),
        sa.Column("data", sa.Text(), nullable=True, comment="project sample result"),
        sa.Column(
            "state",
            sa.String(length=32),
            nullable=True,
            comment="NEW is has not start yet, DONE is completed, SKIPPED is skipped",
        ),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Project delete time",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["user.id"],
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["project_attachment.id"],
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_id"),
    )
    op.create_index(
        "idx_sample_id_deleted_at", "project_sample", ["id", "deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_project_sample_created_by"),
        "project_sample",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_sample_deleted_at"),
        "project_sample",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_sample_project_id"),
        "project_sample",
        ["project_id"],
        unique=False,
    )

    # 8. 创建样本更新者表及其索引。
    op.create_table(
        "project_sample_updater",
        sa.Column("sample_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="created time",
        ),
        sa.ForeignKeyConstraint(
            ["sample_id"], ["project_sample.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("sample_id", "user_id"),
    )
    op.create_index(
        op.f("ix_project_sample_updater_sample_id"),
        "project_sample_updater",
        ["sample_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_sample_updater_user_id"),
        "project_sample_updater",
        ["user_id"],
        unique=False,
    )

    # 训练记录保存参数、执行状态与产物，日志文件放在服务端工作目录。
    op.create_table(
        "training_run",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id", sa.Integer(), sa.ForeignKey("project.id"), nullable=False
        ),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("initial_model", sa.String(256), nullable=False),
        sa.Column("parameters", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=True),
        sa.Column("model_name", sa.String(256), nullable=True),
        sa.Column("metrics", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_training_run_project_id", "training_run", ["project_id"])


def downgrade() -> None:
    """按外键依赖的逆序删除初始化脚本创建的索引和业务表。"""
    op.drop_index("ix_training_run_project_id", table_name="training_run")
    op.drop_table("training_run")

    op.drop_index(
        op.f("ix_project_sample_updater_user_id"), table_name="project_sample_updater"
    )
    op.drop_index(
        op.f("ix_project_sample_updater_sample_id"), table_name="project_sample_updater"
    )

    op.drop_table("project_sample_updater")
    op.drop_index(op.f("ix_project_sample_project_id"), table_name="project_sample")
    op.drop_index(op.f("ix_project_sample_deleted_at"), table_name="project_sample")
    op.drop_index(op.f("ix_project_sample_created_by"), table_name="project_sample")
    op.drop_index("idx_sample_id_deleted_at", table_name="project_sample")

    op.drop_table("project_sample")
    op.drop_index(
        op.f("ix_project_pre_annotation_project_id"),
        table_name="project_pre_annotation",
    )
    op.drop_index(
        op.f("ix_project_pre_annotation_sample_name"),
        table_name="project_pre_annotation",
    )
    op.drop_index(
        op.f("ix_project_pre_annotation_file_id"), table_name="project_pre_annotation"
    )
    op.drop_index(
        op.f("ix_project_pre_annotation_deleted_at"),
        table_name="project_pre_annotation",
    )
    op.drop_index(
        op.f("ix_project_pre_annotation_created_by"),
        table_name="project_pre_annotation",
    )
    op.drop_index(
        "idx_pre_annotation_id_deleted_at", table_name="project_pre_annotation"
    )

    op.drop_table("project_pre_annotation")
    op.drop_index(
        op.f("ix_project_collaborator_user_id"), table_name="project_collaborator"
    )
    op.drop_index(
        op.f("ix_project_collaborator_project_id"), table_name="project_collaborator"
    )

    op.drop_table("project_collaborator")
    op.drop_index(
        op.f("ix_project_attachment_updated_by"), table_name="project_attachment"
    )
    op.drop_index(
        op.f("ix_project_attachment_project_id"), table_name="project_attachment"
    )
    op.drop_index(
        op.f("ix_project_attachment_deleted_at"), table_name="project_attachment"
    )
    op.drop_index(
        op.f("ix_project_attachment_created_by"), table_name="project_attachment"
    )
    op.drop_index("idx_attachment_id_deleted_at", table_name="project_attachment")

    op.drop_table("project_attachment")
    op.drop_index(op.f("ix_auto_label_job_project_id"), table_name="auto_label_job")

    op.drop_table("auto_label_job")
    op.drop_index(op.f("ix_project_name"), table_name="project")
    op.drop_index(op.f("ix_project_deleted_at"), table_name="project")
    op.drop_index(op.f("ix_project_created_by"), table_name="project")
    op.drop_index("idx_project_id_deleted_at_index", table_name="project")

    op.drop_table("project")

    op.drop_index(op.f("ix_user_username"), table_name="user")

    op.drop_index("ix_access_token_user_id", table_name="access_token")
    op.drop_table("access_token")

    op.drop_table("user")
