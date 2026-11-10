"""发行包构建时打包前端；开发安装继续使用独立 Vite 服务。"""

import shutil
import subprocess
import re
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.metadata.plugin.interface import MetadataHookInterface


def _project_readme(root: Path) -> Path:
    """源码仓库以首页为准；源码包使用构建时携带的同一份首页。"""
    bundled = root / "PROJECT_README.md"
    return bundled if bundled.is_file() else root.parent / "README.md"


class ProjectMetadataHook(MetadataHookInterface):
    """PyPI 与 GitHub 共用产品介绍，仅转换发布页所需的相对链接。"""

    def update(self, metadata: dict) -> None:
        content = _project_readme(Path(self.root)).read_text(encoding="utf-8")

        def absolute(target: str, image: bool = False) -> str:
            if target.startswith(("#", "/")) or re.match(r"[\w+.-]+:", target):
                return target
            base = (
                "https://raw.githubusercontent.com/killf/LabelS/main/"
                if image
                else "https://github.com/killf/LabelS/blob/main/"
            )
            return base + target.removeprefix("./")

        # 1. Markdown 图片和文档链接转为远程地址，页内锚点保留。
        content = re.sub(
            r"(!?\[[^\]]*\]\()([^\s)]+)(\))",
            lambda match: match[1]
            + absolute(match[2], match[1].startswith("!"))
            + match[3],
            content,
        )
        # 2. 首页 Logo 使用 HTML 图片，同样需要可供 PyPI 访问的地址。
        content = re.sub(
            r'(src=")([^"]+)(")',
            lambda match: match[1] + absolute(match[2], True) + match[3],
            content,
        )
        metadata["readme"] = {"content-type": "text/markdown", "text": content}


class FrontendBuildHook(BuildHookInterface):
    """从源码构建前端，或复用 sdist 中已经打包的资源，交给 Hatch 写入发行包。"""

    def initialize(self, version: str, build_data: dict) -> None:
        if version == "editable":
            return

        # 1. 源码构建始终重建页面，避免把旧 dist 静默带进新版本。
        root = Path(self.root)
        if self.target_name == "sdist":
            build_data.setdefault("force_include", {})[
                str(_project_readme(root))
            ] = "PROJECT_README.md"
        frontend = root.parent / "frontend"
        static = root / "statics"
        if (frontend / "package.json").is_file():
            pnpm = shutil.which("pnpm")
            if pnpm is None:
                raise RuntimeError("构建发行包需要 pnpm，请先准备 README 中的前端环境")
            subprocess.run([pnpm, "build:frontend"], cwd=frontend, check=True)
            static = frontend / "apps/frontend/dist"

        # 2. sdist 已携带资源，转换为 wheel 时无需 Node.js 或 pnpm。
        if not (static / "index.html").is_file():
            raise RuntimeError("发行包缺少前端 index.html，请从完整源码仓库构建")
        destination = "backend/statics" if self.target_name == "wheel" else "statics"
        build_data.setdefault("force_include", {})[str(static)] = destination
