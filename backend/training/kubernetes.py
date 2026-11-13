"""本机经 kubectl 传输训练输入与产物；Pod 端入口复用项目训练命令。"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath, PureWindowsPath
from uuid import uuid4

FRAMEWORK_REQUIREMENT = "ultralytics==8.4.203"
SOURCE_FILES = (
    "__init__.py",
    "application/__init__.py",
    "application/command/__init__.py",
    "application/command/training.py",
    "common/__init__.py",
    "common/config.py",
    "common/storage.py",
    "inference.py",
    "training/__init__.py",
    "training/train.py",
    "training/control.py",
    "training/kubernetes.py",
)

# 1. 主进程保持运行，训练子进程不依赖本机 exec 连接；产物回收前不退出容器。
BOOTSTRAP = """
import pathlib, runpy, time
print('Waiting for training input upload', flush=True)
while not pathlib.Path('/workspace/input.ready').exists():
    time.sleep(1)
runpy.run_path('/workspace/code/backend/training/kubernetes.py', run_name='__main__')
"""

POLL = """
import json, pathlib, sys
if sys.argv[1] == 'pause':
    pathlib.Path('/workspace/run/pause.request').touch()
path = pathlib.Path('/workspace/exit.json')
print(path.read_text() if path.is_file() else 'null')
"""


class KubernetesError(RuntimeError):
    """只包含可公开的操作说明，不携带 kubectl 凭据或原始认证错误。"""


def validate_environment(kubeconfig: Path | None) -> None:
    """检查本机文件与 CLI 是否存在；不读取 kubeconfig 内容或访问集群。"""
    if kubeconfig is None or not kubeconfig.expanduser().is_file():
        raise KubernetesError("Kubeconfig 文件不存在，请检查 YOLO_MCP_KUBECONFIG")
    if shutil.which("kubectl") is None:
        raise KubernetesError("本机未安装 kubectl，或 kubectl 不在 PATH 中")


def _save(workspace: Path, state: dict) -> None:
    """将当前连接引用和执行阶段原子写入 run，避免服务重启读取半份 JSON。"""
    temporary = workspace / "kubernetes.tmp"
    temporary.write_text(json.dumps(state), encoding="utf-8")
    temporary.replace(workspace / "kubernetes.json")


def prepare(
    workspace: Path,
    kubeconfig: Path,
    namespace: str,
    image: str,
    *,
    vci_instance_family: str = "",
    vci_gpu_driver_version: str = "",
    vci_zone: str = "",
) -> None:
    """在本次 run 保存连接引用和唯一 Pod 名称，不保存认证材料或修改集群。"""
    _save(
        workspace,
        {
            "kubeconfig": str(kubeconfig.expanduser().resolve()),
            "namespace": namespace,
            "image": image,
            "vci_instance_family": vci_instance_family,
            "vci_gpu_driver_version": vci_gpu_driver_version,
            "vci_zone": vci_zone,
            "pod": f"yolo-mcp-train-{uuid4().hex}",
            "context": None,
            "stage": "new",
        },
    )


def prepare_resume(workspace: Path) -> None:
    """恢复使用原集群配置，分配新 Pod；已回收的本地检查点由新 Pod 继续训练。"""
    state = json.loads((workspace / "kubernetes.json").read_text(encoding="utf-8"))
    validate_environment(Path(state["kubeconfig"]))
    if state["stage"] != "collected":
        raise KubernetesError("远端产物尚未完整回收，不能新建 Pod 恢复训练")
    if (workspace / "train.log").is_file():
        shutil.copy2(workspace / "train.log", workspace / "k8s-previous.log")
    state.update(pod=f"yolo-mcp-train-{uuid4().hex}", stage="new", deleted=False)
    _save(workspace, state)


async def cleanup(workspace: Path) -> None:
    """删除本次记录的远端 Pod；失败时保留连接记录，让调用方停止删除本地文件。"""
    path = workspace / "kubernetes.json"
    if not path.is_file():
        return
    state = json.loads(path.read_text(encoding="utf-8"))
    if not state["context"] or state.get("deleted"):
        return
    validate_environment(Path(state["kubeconfig"]))
    await _command(
        state,
        "delete",
        "pod",
        state["pod"],
        "--ignore-not-found",
        "--wait=true",
        cwd=workspace,
    )
    state["deleted"] = True
    _save(workspace, state)


async def _finish(workspace: Path, state: dict) -> int:
    """回收完成后尝试删除 Pod；清理错误保留到日志，不改变已经落地的训练结果。"""
    try:
        await cleanup(workspace)
    except (KubernetesError, TimeoutError):
        with (workspace / "train.log").open("a", encoding="utf-8") as output:
            output.write(
                f"\nPod 清理失败，请删除远端 Pod：{state['namespace']}/{state['pod']}\n"
            )
    return state["exit_code"]


async def _command(
    state: dict,
    *args: str,
    cwd: Path,
    input: bytes | None = None,
    output=None,
    timeout: int = 60,
    _attempt: int = 0,
) -> bytes:
    """以参数数组调用 kubectl，固定 kubeconfig、context 和 namespace，清理取消的 CLI。"""
    command = [
        "kubectl",
        "--kubeconfig",
        state["kubeconfig"],
        "--namespace",
        state["namespace"],
    ]
    if state["context"]:
        command.extend(["--context", state["context"]])
    position = output.tell() if output is not None else None
    process = await asyncio.create_subprocess_exec(
        *command,
        *args,
        cwd=str(cwd),
        stdin=(
            asyncio.subprocess.PIPE if input is not None else asyncio.subprocess.DEVNULL
        ),
        stdout=output if output is not None else asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(input), timeout)
    except (asyncio.CancelledError, TimeoutError):
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    if process.returncode:
        # 仅提取固定错误类别，不输出可能包含认证信息、代理地址或证书路径的原始 stderr。
        error_text = stderr.decode("utf-8", errors="replace")
        match = re.search(r"Error from server \(([A-Za-z]+)\)", error_text)
        reason = match.group(1) if match else "UnknownError"
        if not match:
            for marker, category in (
                ("timeout", "ConnectionTimeout"),
                ("connection attempt failed", "ConnectionTimeout"),
                ("EOF", "UnexpectedEOF"),
                ("connection reset", "ConnectionReset"),
                ("forcibly closed", "ConnectionReset"),
                ("connection refused", "ConnectionRefused"),
                ("certificate", "CertificateError"),
            ):
                if marker in error_text:
                    reason = category
                    break
        # 只重试幂等读取，短暂网络波动不终止已在远端运行的训练。
        if (
            args[0] in {"get", "logs"}
            and _attempt < 2
            and reason
            in {
                "ConnectionTimeout",
                "UnexpectedEOF",
                "ConnectionReset",
                "ServiceUnavailable",
                "TooManyRequests",
                "InternalError",
            }
        ):
            if output is not None:
                output.seek(position)
                output.truncate()
                output.flush()
            await asyncio.sleep(1)
            return await _command(
                state,
                *args,
                cwd=cwd,
                input=input,
                output=output,
                timeout=timeout,
                _attempt=_attempt + 1,
            )
        raise KubernetesError(
            f"kubectl {args[0]} 失败（退出码 {process.returncode}，{reason}）；"
            f"请检查连接和权限。远端 Pod：{state['namespace']}/{state['pod']}"
        )
    return stdout or b""


def _manifest(state: dict) -> dict:
    """从本次配置生成单卡 Pod 清单，使用临时工作卷，不挂载本机配置。"""
    manifest = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": state["pod"],
            "namespace": state["namespace"],
            "labels": {"app.kubernetes.io/name": "yolo-mcp-training"},
        },
        "spec": {
            "restartPolicy": "Never",
            "containers": [
                {
                    "name": "trainer",
                    "image": state["image"],
                    "workingDir": "/workspace",
                    "command": ["python", "-u", "-c", BOOTSTRAP],
                    "env": [
                        {"name": "PYTHONUNBUFFERED", "value": "1"},
                        {"name": "PYTHONIOENCODING", "value": "utf-8"},
                        {"name": "PYTHONPATH", "value": "/workspace/code"},
                        {"name": "YOLO_AUTOINSTALL", "value": "false"},
                        {"name": "YOLO_CONFIG_DIR", "value": "/workspace/.ultralytics"},
                        {"name": "YOLO_MCP_DATA_DIR", "value": "/workspace/data"},
                    ],
                    "resources": {"limits": {"nvidia.com/gpu": 1}},
                    "volumeMounts": [{"name": "workspace", "mountPath": "/workspace"}],
                }
            ],
            "volumes": [{"name": "workspace", "emptyDir": {}}],
        },
    }
    family = state.get("vci_instance_family")
    if family:
        manifest["metadata"]["annotations"] = {
            "vke.volcengine.com/burst-to-vci": "enforce",
            "vci.vke.volcengine.com/preferred-instance-family": family,
        }
        driver = state.get("vci_gpu_driver_version")
        if driver:
            manifest["metadata"]["annotations"][
                "vci.vke.volcengine.com/gpu-driver-version"
            ] = driver
        manifest["spec"]["nodeSelector"] = {"type": "virtual-kubelet"}
        if state.get("vci_zone"):
            manifest["spec"]["nodeSelector"]["topology.kubernetes.io/zone"] = state[
                "vci_zone"
            ]
        manifest["spec"]["tolerations"] = [
            {
                "key": "vci.vke.volcengine.com/node-type",
                "operator": "Equal",
                "value": "vci",
                "effect": "NoSchedule",
            }
        ]
    return manifest


async def _initial_model(model: str, cache: Path) -> Path:
    """复用项目权重或本机公共缓存；官方权重按需流式下载，不加载本机 PyTorch。"""
    from backend.training.train import OFFICIAL_MODELS

    if model not in OFFICIAL_MODELS:
        path = Path(model)
        if not path.is_file():
            raise KubernetesError("初始模型文件不存在")
        return path
    path = cache / model
    if path.is_file():
        return path
    import httpx

    cache.mkdir(parents=True, exist_ok=True)
    # 独立临时文件只用于完整下载后替换缓存，不引入跨项目锁或占号流程。
    with tempfile.NamedTemporaryFile(dir=cache, suffix=".tmp", delete=False) as file:
        temporary = Path(file.name)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
            url = f"https://github.com/ultralytics/assets/releases/download/v8.4.0/{model}"
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with temporary.open("wb") as file:
                    async for chunk in response.aiter_bytes():
                        file.write(chunk)
        if temporary.stat().st_size < 100000:
            raise KubernetesError("官方初始模型下载不完整")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _pack_input(workspace: Path, model: Path, args: list[str]) -> None:
    """只打包本次数据快照、初始模型、检查点和代码白名单，不扫描配置或凭据。"""
    root = Path(__file__).resolve().parents[1]
    (workspace / "arguments.json").write_text(json.dumps(args), encoding="utf-8")
    with tarfile.open(workspace / "k8s-input.tar", "w") as archive:
        for relative in SOURCE_FILES:
            archive.add(root / relative, f"code/backend/{relative}", recursive=False)
        archive.add(model, "initial.pt", recursive=False)
        archive.add(workspace / "arguments.json", "arguments.json", recursive=False)
        dataset = workspace / "dataset"
        for path in dataset.rglob("*"):
            if path.is_symlink() or not path.resolve().is_relative_to(
                dataset.resolve()
            ):
                raise KubernetesError("训练快照不能包含符号链接或越界路径")
            if path.is_file():
                archive.add(
                    path,
                    f"run/dataset/{path.relative_to(dataset).as_posix()}",
                    recursive=False,
                )
        checkpoint = workspace / "resume.pt"
        if checkpoint.is_file():
            archive.add(checkpoint, "run/resume.pt", recursive=False)


async def _logs(state: dict, workspace: Path, *, full: bool = False) -> None:
    """同步 Pod 日志到本地，恢复训练时保留上一段日志，失败不覆盖可读日志。"""
    temporary = workspace / "k8s-log.tmp"
    try:
        with temporary.open("wb") as output:
            previous = workspace / "k8s-previous.log"
            if previous.is_file():
                with previous.open("rb") as input:
                    shutil.copyfileobj(input, output)
                output.write(b"\n--- Resumed Kubernetes training ---\n")
            output.flush()
            await _command(
                state,
                "logs",
                state["pod"],
                "-c",
                "trainer",
                *([] if full else ["--tail=1000"]),
                cwd=workspace,
                output=output,
            )
        temporary.replace(workspace / "train.log")
    finally:
        temporary.unlink(missing_ok=True)


def _unpack_result(workspace: Path, models: Path, code: int) -> None:
    """校验回传路径与必需产物，替换本地训练输出，并为模型分配本项目日期编号。"""
    from backend.training.train import PAUSED_EXIT_CODE, _next_run_id

    with tempfile.TemporaryDirectory(dir=workspace) as directory:
        staging = Path(directory)
        with tarfile.open(workspace / "k8s-result.tar") as archive:
            for member in archive.getmembers():
                path = PurePosixPath(member.name)
                if (
                    not path.parts
                    or path.parts[0] not in {"run", "models"}
                    or (
                        path.parts[0] == "run"
                        and len(path.parts) > 1
                        and path.parts[1]
                        not in {
                            "result.json",
                            "resume.pt",
                            "train.log",
                            "training",
                            "input",
                        }
                    )
                    or path.is_absolute()
                    or ".." in path.parts
                    or "\\" in member.name
                    or ":" in member.name
                    or not (member.isfile() or member.isdir())
                ):
                    raise KubernetesError("远端产物包含无效路径或链接")
            archive.extractall(staging, filter="data")
        result_path = staging / "run/result.json"
        result = (
            json.loads(result_path.read_text(encoding="utf-8"))
            if result_path.is_file()
            else {}
        )
        if code == 0:
            name = result.get("model_name", "")
            if (
                not name
                or PurePosixPath(name).name != name
                or PureWindowsPath(name).name != name
                or not name.endswith(".pt")
            ):
                raise KubernetesError("远端训练未返回有效的模型文件名")
            source = staging / "models" / name
            if not source.is_file() or not isinstance(result.get("metrics"), dict):
                raise KubernetesError("远端训练模型或指标缺失，Pod 已保留")
            models.mkdir(parents=True, exist_ok=True)
            run_id = _next_run_id(models.parent)
            target = models / f"{run_id}.pt"
            shutil.copy2(source, target)
            result.update(run_id=run_id, model_name=target.name, model_path=str(target))
        elif code == PAUSED_EXIT_CODE and not (staging / "run/resume.pt").is_file():
            raise KubernetesError("远端暂停检查点缺失，Pod 已保留")
        if result:
            (staging / "run/result.json").write_text(
                json.dumps(result), encoding="utf-8"
            )
        for path in (staging / "run").iterdir():
            target = workspace / path.name
            if (
                not target.resolve().is_relative_to(workspace.resolve())
                or target == workspace
                or target.is_symlink()
            ):
                raise KubernetesError("远端产物目标越出运行目录")
            if target.is_dir():
                shutil.rmtree(target)
            if path.name == "train.log":
                with target.open("wb") as output:
                    previous = workspace / "k8s-previous.log"
                    if previous.is_file():
                        with previous.open("rb") as input:
                            shutil.copyfileobj(input, output)
                        output.write(b"\n--- Resumed Kubernetes training ---\n")
                    with path.open("rb") as input:
                        shutil.copyfileobj(input, output)
                continue
            shutil.move(str(path), str(target))


async def execute(
    workspace: Path, models: Path, model: str, cache: Path, args: list[str]
) -> int:
    """创建或重连同一 Pod，传输输入、同步日志与暂停请求，回收后清理 Pod并返回退出码。"""
    state = json.loads((workspace / "kubernetes.json").read_text(encoding="utf-8"))
    if state["stage"] == "collected":
        return await _finish(workspace, state)
    validate_environment(Path(state["kubeconfig"]))
    if not state["context"]:
        state["context"] = (
            (await _command(state, "config", "current-context", cwd=workspace))
            .decode()
            .strip()
        )
        if not state["context"]:
            raise KubernetesError("Kubeconfig 未选择 current-context")
        _save(workspace, state)

    # 1. 创建前查询唯一 Pod 名，服务重启只重连原任务，不重跑已启动的训练。
    existing = await _command(
        state,
        "get",
        "pod",
        state["pod"],
        "--ignore-not-found",
        "-o",
        "json",
        cwd=workspace,
    )
    if not existing.strip():
        if state["stage"] != "new":
            raise KubernetesError("远端训练 Pod 已丢失，不会自动重跑训练")
        await _command(
            state,
            "create",
            "-f",
            "-",
            cwd=workspace,
            input=json.dumps(_manifest(state)).encode(),
        )
        state["stage"] = "created"
        _save(workspace, state)
    deadline = time.monotonic() + 600
    while True:
        pod = json.loads(
            await _command(
                state, "get", "pod", state["pod"], "-o", "json", cwd=workspace
            )
        )
        status = pod.get("status", {})
        if status.get("phase") in {"Failed", "Succeeded"}:
            await _logs(state, workspace)
            raise KubernetesError("训练容器已退出，无法使用 kubectl cp 回收产物")
        containers = status.get("containerStatuses", [])
        if any("running" in item.get("state", {}) for item in containers):
            break
        if time.monotonic() >= deadline:
            raise KubernetesError(
                "等待训练 Pod 启动超时，请检查 GPU 调度、镜像和 namespace 配额"
            )
        await asyncio.sleep(3)

    # 2. 本机上传完整 tar 后才写入就绪标记，Windows 本地文件参数使用相对路径。
    if state["stage"] != "uploaded":
        ready = await _command(
            state,
            "exec",
            state["pod"],
            "-c",
            "trainer",
            "--",
            "python",
            "-c",
            "from pathlib import Path; print(int(Path('/workspace/input.ready').exists()))",
            cwd=workspace,
        )
        if ready.strip() != b"1":
            weights = await _initial_model(model, cache)
            await asyncio.to_thread(_pack_input, workspace, weights, args)
            try:
                await _command(
                    state,
                    "cp",
                    "k8s-input.tar",
                    f"{state['pod']}:/workspace/input.tar",
                    "-c",
                    "trainer",
                    cwd=workspace,
                    timeout=3600,
                )
                await _command(
                    state,
                    "exec",
                    state["pod"],
                    "-c",
                    "trainer",
                    "--",
                    "python",
                    "-c",
                    "import tarfile; from pathlib import Path; "
                    "tarfile.open('/workspace/input.tar').extractall('/workspace', filter='data'); "
                    "Path('/workspace/input.tar').unlink(); Path('/workspace/input.ready').touch()",
                    cwd=workspace,
                    timeout=3600,
                )
            finally:
                (workspace / "k8s-input.tar").unlink(missing_ok=True)
        state["stage"] = "uploaded"
        _save(workspace, state)

    while True:
        await _logs(state, workspace)
        result = json.loads(
            await _command(
                state,
                "exec",
                state["pod"],
                "-c",
                "trainer",
                "--",
                "python",
                "-c",
                POLL,
                "pause" if (workspace / "pause.request").is_file() else "poll",
                cwd=workspace,
            )
        )
        if result is not None:
            code = result["exit_code"]
            break
        await asyncio.sleep(3)

    # 3. 只回传输出，不重新下载图片；回收失败保留运行中的容器与 emptyDir。
    await _logs(state, workspace, full=True)
    await _command(
        state,
        "cp",
        f"{state['pod']}:/workspace/output.tar",
        "k8s-result.tar",
        "-c",
        "trainer",
        cwd=workspace,
        timeout=3600,
    )
    try:
        await asyncio.to_thread(_unpack_result, workspace, models, code)
    finally:
        (workspace / "k8s-result.tar").unlink(missing_ok=True)
    state.update(stage="collected", exit_code=code)
    _save(workspace, state)
    return await _finish(workspace, state)


def _pod_main(workspace: Path = Path("/workspace")) -> None:
    """Pod 内安装轻量依赖并复用现有 CLI；打包输出后等待本机回收，不替换 GPU 框架。"""
    code = 1
    try:
        # 1. 官方镜像提供 GPU 版 torch；固定项目使用的 Ultralytics，不更新 torch。
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "pydantic>=2,<3",
                "pydantic-settings>=2,<3",
                "loguru>=0.6",
                "pyyaml>=6,<7",
                "tzdata>=2025.2",
            ],
            check=True,
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-deps",
                FRAMEWORK_REQUIREMENT,
            ],
            check=True,
        )
        args = json.loads((workspace / "arguments.json").read_text(encoding="utf-8"))
        # 训练输出同时写容器 stdout 和工作卷，避免 kubelet 日志轮转丢失早期 epoch。
        with (workspace / "run/train.log").open("wb") as log:
            with subprocess.Popen(
                args,
                cwd=workspace / "code",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            ) as process:
                while chunk := process.stdout.read1(65536):
                    log.write(chunk)
                    log.flush()
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.buffer.flush()
                code = process.wait()
    except Exception as error:
        print(f"Training bootstrap failed: {type(error).__name__}", flush=True)

    # 2. 无论训练成功、暂停或失败均回传已有输出；退出码最后原子写入。
    with tarfile.open(workspace / "output.tar", "w") as archive:
        for name in ("result.json", "resume.pt", "train.log", "training", "input"):
            path = workspace / "run" / name
            if path.exists():
                archive.add(path, f"run/{name}")
        archive.add(workspace / "run", "run", recursive=False)
        if (workspace / "models").is_dir():
            archive.add(workspace / "models", "models")
    temporary = workspace / "exit.tmp"
    temporary.write_text(json.dumps({"exit_code": code}), encoding="utf-8")
    temporary.replace(workspace / "exit.json")
    print(
        f"Training exited with code {code}; waiting for artifact collection", flush=True
    )
    while True:
        time.sleep(60)


if __name__ == "__main__":
    _pod_main()
