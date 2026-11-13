"""验证远端训练的文件边界、传输顺序、回收与断线重连，不访问真实集群。"""

import asyncio
import io
import json
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

import pytest
import httpx
from pydantic import ValidationError

from backend.common.config import Settings
from backend.training import kubernetes as k8s


@pytest.fixture
def remote_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "run"
    (workspace / "dataset/images").mkdir(parents=True)
    (workspace / "dataset/images/1.jpg").write_bytes(b"image")
    (workspace / "dataset/data.yaml").write_text("train: train.txt\n")
    (workspace / "resume.pt").write_bytes(b"checkpoint")
    model = tmp_path / "initial.pt"
    model.write_bytes(b"initial weights")
    kubeconfig = tmp_path / "fake-kubeconfig"
    kubeconfig.write_text("test placeholder; never parsed")
    monkeypatch.setattr(k8s.shutil, "which", lambda _: "fake-kubectl")
    k8s.prepare(workspace, kubeconfig, "training-test", "example/ultralytics:gpu")
    return workspace, model


def write_outputs(path, code=0, model_name="remote.pt"):
    with tarfile.open(path, "w") as archive:
        entries = {"run/training/results.csv": b"epoch,loss\n1,0.2\n"}
        if code == 0:
            entries["run/result.json"] = json.dumps(
                {
                    "run_id": "remote",
                    "model_name": model_name,
                    "metrics": {"metrics/mAP50(B)": 0.75},
                }
            ).encode()
            entries[f"models/{model_name}"] = b"trained weights"
        elif code == 75:
            entries["run/resume.pt"] = b"paused checkpoint"
            entries["run/result.json"] = b'{"status":"PAUSED"}'
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))


def test_settings_read_explicit_remote_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("YOLO_MCP_KUBECONFIG", str(tmp_path / "fake-config"))
    monkeypatch.setenv("YOLO_MCP_K8S_NAMESPACE", "training-gpu")
    monkeypatch.setenv("YOLO_MCP_K8S_IMAGE", "registry.example/train:fixed")
    config = Settings()
    assert config.KUBECONFIG == tmp_path / "fake-config"
    assert config.K8S_NAMESPACE == "training-gpu"
    assert config.K8S_IMAGE == "registry.example/train:fixed"
    monkeypatch.setenv("YOLO_MCP_K8S_VCI_INSTANCE_FAMILY", "vci.gni3")
    monkeypatch.setenv("YOLO_MCP_K8S_VCI_GPU_DRIVER_VERSION", "tesla-570.195.03")
    vci = Settings()
    assert vci.K8S_VCI_INSTANCE_FAMILY == "vci.gni3"
    assert vci.K8S_VCI_GPU_DRIVER_VERSION == "tesla-570.195.03"
    monkeypatch.setenv("YOLO_MCP_K8S_NAMESPACE", "bad/namespace")
    with pytest.raises(ValidationError):
        Settings()


def test_vci_manifest_forces_virtual_gpu_node_and_retains_resume_settings(
    remote_workspace,
):
    workspace, _ = remote_workspace
    state = json.loads((workspace / "kubernetes.json").read_text())
    state.update(
        vci_instance_family="vci.gni3",
        vci_gpu_driver_version="tesla-570.195.03",
        vci_zone="cn-beijing-a",
        stage="collected",
        deleted=True,
    )
    k8s._save(workspace, state)
    k8s.prepare_resume(workspace)
    resumed = json.loads((workspace / "kubernetes.json").read_text())
    pod = k8s._manifest(resumed)
    assert pod["metadata"]["annotations"] == {
        "vke.volcengine.com/burst-to-vci": "enforce",
        "vci.vke.volcengine.com/preferred-instance-family": "vci.gni3",
        "vci.vke.volcengine.com/gpu-driver-version": "tesla-570.195.03",
    }
    assert pod["spec"]["nodeSelector"] == {
        "type": "virtual-kubelet",
        "topology.kubernetes.io/zone": "cn-beijing-a",
    }
    assert pod["spec"]["tolerations"][0]["value"] == "vci"
    assert pod["spec"]["containers"][0]["resources"]["limits"] == {"nvidia.com/gpu": 1}


def test_input_contains_only_snapshot_model_checkpoint_and_runtime(remote_workspace):
    workspace, model = remote_workspace
    (workspace / "secret.key").write_text("synthetic secret")
    (workspace / ".env").write_text("SYNTHETIC_SECRET=not-real")
    k8s._pack_input(
        workspace, model, ["python", "-m", "backend.training.train", "--help"]
    )
    with tarfile.open(workspace / "k8s-input.tar") as archive:
        names = archive.getnames()
        assert "initial.pt" in names
        assert "run/resume.pt" in names
        assert "run/dataset/images/1.jpg" in names
        assert not any(
            "kubeconfig" in name or ".env" in name or "secret.key" in name
            for name in names
        )
        assert "kubernetes.json" not in names
        extracted = workspace / "extracted"
        archive.extractall(extracted, filter="data")
    # 实际从传输包启动训练 CLI；帮助路径不需要 GPU 或训练依赖。
    process = subprocess.run(
        [sys.executable, "-m", "backend.training.train", "--help"],
        cwd=extracted / "code",
        capture_output=True,
    )
    assert process.returncode == 0, process.stderr.decode(errors="replace")
    assert b"--resume-checkpoint" in process.stdout
    project = tomllib.loads(
        (Path(k8s.__file__).parents[1] / "pyproject.toml").read_text()
    )
    assert (
        k8s.FRAMEWORK_REQUIREMENT
        in project["project"]["optional-dependencies"]["training"]
    )


@pytest.mark.parametrize("code", [0, 75, 1])
def test_transfer_collects_before_deleting_and_respects_pause(
    remote_workspace, monkeypatch, code
):
    workspace, model = remote_workspace
    models = workspace.parent / "project/models"
    models.mkdir(parents=True)
    (workspace / "pause.request").touch()
    commands = []

    async def command(state, *args, cwd, input=None, output=None, **kwargs):
        commands.append(args)
        assert cwd == workspace
        assert state["namespace"] == "training-test"
        if args[0] == "config":
            return b"test-context\n"
        if args[0] == "get":
            if "--ignore-not-found" in args:
                return b""
            return b'{"status":{"phase":"Running","containerStatuses":[{"state":{"running":{}}}]}}'
        if args[0] == "create":
            pod = json.loads(input)
            container = pod["spec"]["containers"][0]
            assert container["image"] == "example/ultralytics:gpu"
            assert container["resources"]["limits"] == {"nvidia.com/gpu": 1}
            assert pod["spec"]["restartPolicy"] == "Never"
            assert "hostNetwork" not in pod["spec"]
            assert not any(
                "kubeconfig" in json.dumps(volume).lower()
                for volume in pod["spec"]["volumes"]
            )
        if args[0] == "logs":
            output.write(b"remote epoch log\n")
        if args[0] == "exec":
            if k8s.POLL in args:
                assert args[-1] == "pause"
                return json.dumps({"exit_code": code}).encode()
            if "input.ready" in args[-1] and "print" in args[-1]:
                return b"0\n"
        if args[0] == "cp":
            if args[1] == "k8s-input.tar":
                assert Path(args[1]).is_absolute() is False
                assert (cwd / args[1]).is_file()
            else:
                write_outputs(cwd / args[2], code)
        if args[0] == "delete":
            assert (
                json.loads((workspace / "kubernetes.json").read_text())["stage"]
                == "collected"
            )
            if code == 0:
                assert len(list(models.glob("*.pt"))) == 1
            elif code == 75:
                assert (workspace / "resume.pt").read_bytes() == b"paused checkpoint"
        return b""

    monkeypatch.setattr(k8s, "_command", command)
    result = asyncio.run(
        k8s.execute(workspace, models, str(model), workspace / "cache", ["python"])
    )
    assert result == code
    assert commands[-1][0] == "delete"
    assert (workspace / "train.log").read_bytes() == b"remote epoch log\n"
    assert not (workspace / "k8s-input.tar").exists()
    if code == 0:
        result = json.loads((workspace / "result.json").read_text())
        assert (models / result["model_name"]).read_bytes() == b"trained weights"
        assert result["run_id"] != "remote"


@pytest.mark.parametrize("failure", ["upload", "collection"])
def test_transfer_failure_keeps_pod_and_connection_record(
    remote_workspace, monkeypatch, failure
):
    workspace, model = remote_workspace
    commands = []

    async def command(state, *args, **kwargs):
        commands.append(args)
        if args[0] == "config":
            return b"test-context"
        if args[0] == "get":
            return b'{"status":{"containerStatuses":[{"state":{"running":{}}}]}}'
        if args[0] == "logs":
            kwargs["output"].write(b"training log")
        if args[0] == "exec":
            if k8s.POLL in args:
                return b'{"exit_code":0}'
            return b"0"
        if args[0] == "cp":
            if failure == "upload" or args[1] != "k8s-input.tar":
                raise k8s.KubernetesError("synthetic disconnected transfer")
        return b""

    monkeypatch.setattr(k8s, "_command", command)
    with pytest.raises(k8s.KubernetesError):
        asyncio.run(
            k8s.execute(
                workspace, workspace / "models", str(model), workspace / "cache", []
            )
        )
    assert not any(args[0] == "delete" for args in commands)
    state = json.loads((workspace / "kubernetes.json").read_text())
    assert state["pod"] and state["stage"] != "collected"


def test_reconnect_collects_original_pod_without_upload_or_training(
    remote_workspace, monkeypatch
):
    workspace, _ = remote_workspace
    state = json.loads((workspace / "kubernetes.json").read_text())
    state.update(context="original-context", stage="uploaded")
    k8s._save(workspace, state)
    seen = []

    async def command(current, *args, **kwargs):
        assert current["pod"] == state["pod"]
        assert current["context"] == "original-context"
        seen.append(args)
        if args[0] == "get":
            return b'{"status":{"containerStatuses":[{"state":{"running":{}}}]}}'
        if args[0] == "logs":
            kwargs["output"].write(b"reconnected log")
        if args[0] == "exec":
            return b'{"exit_code":0}'
        if args[0] == "cp":
            write_outputs(workspace / args[2])
        return b""

    monkeypatch.setattr(k8s, "_command", command)
    asyncio.run(
        k8s.execute(
            workspace, workspace / "models", "missing.pt", workspace / "cache", []
        )
    )
    assert not any(args[0] in {"config", "create"} for args in seen)
    assert not any(args[:2] == ("cp", "k8s-input.tar") for args in seen)


@pytest.mark.parametrize("name", ["../escaped.pt", "C:\\escaped.pt", "/escaped.pt"])
def test_malicious_result_does_not_publish_or_escape_workspace(remote_workspace, name):
    workspace, _ = remote_workspace
    write_outputs(workspace / "k8s-result.tar", model_name=name)
    with pytest.raises(k8s.KubernetesError):
        k8s._unpack_result(workspace, workspace / "models", 0)
    assert not list((workspace / "models").glob("*.pt"))


@pytest.mark.parametrize(
    "stderr, reason",
    [
        (b"SYNTHETIC_TOKEN=never-return-this", "UnknownError"),
        (b"Error from server (NotFound): private resource name", "NotFound"),
        (b"Unable to connect to the server: unexpected EOF", "UnexpectedEOF"),
        (b"Unable to connect to the server: i/o timeout", "ConnectionTimeout"),
        (
            b"Unable to connect to the server: connectex: A connection attempt failed because the connected party did not properly respond",
            "ConnectionTimeout",
        ),
    ],
)
def test_kubectl_binds_context_namespace_and_does_not_expose_stderr(
    remote_workspace, monkeypatch, stderr, reason
):
    workspace, _ = remote_workspace
    state = json.loads((workspace / "kubernetes.json").read_text())
    state["context"] = "fixed-context"
    calls = []

    class Process:
        returncode = 1

        async def communicate(self, input):
            return b"", stderr

    async def spawn(*args, **kwargs):
        calls.append((args, kwargs))
        return Process()

    monkeypatch.setattr(k8s.asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(k8s.KubernetesError) as error:
        asyncio.run(k8s._command(state, "get", "pod", state["pod"], cwd=workspace))
    assert "SYNTHETIC_TOKEN" not in str(error.value)
    assert reason in str(error.value)
    args, options = calls[0]
    assert args[:7] == (
        "kubectl",
        "--kubeconfig",
        state["kubeconfig"],
        "--namespace",
        "training-test",
        "--context",
        "fixed-context",
    )
    assert "shell" not in options


def test_official_model_download_uses_host_cache_without_training_runtime(
    tmp_path, monkeypatch
):
    requests = []

    def respond(request):
        requests.append(request)
        assert request.url.path.endswith("/v8.4.0/yolo26n.pt")
        return httpx.Response(200, content=b"x" * 100001)

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(**kwargs, transport=httpx.MockTransport(respond)),
    )
    first = asyncio.run(k8s._initial_model("yolo26n.pt", tmp_path))
    second = asyncio.run(k8s._initial_model("yolo26n.pt", tmp_path))
    assert first == second
    assert first.stat().st_size == 100001
    assert len(requests) == 1
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("operation", ["get", "create", "cp", "exec"])
def test_connection_retry_is_limited_to_reads(remote_workspace, monkeypatch, operation):
    workspace, _ = remote_workspace
    state = json.loads((workspace / "kubernetes.json").read_text())
    launches = []

    class Process:
        def __init__(self, code):
            self.returncode = code

        async def communicate(self, input):
            return (
                b"ready",
                b"Unable to connect to the server: connectex: A connection attempt failed",
            )

    async def spawn(*args, **kwargs):
        launches.append(args)
        return Process(1 if len(launches) == 1 else 0)

    async def immediate(_):
        pass

    monkeypatch.setattr(k8s.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(k8s.asyncio, "sleep", immediate)
    if operation == "get":
        assert asyncio.run(k8s._command(state, operation, cwd=workspace)) == b"ready"
        assert len(launches) == 2
    else:
        with pytest.raises(k8s.KubernetesError):
            asyncio.run(k8s._command(state, operation, cwd=workspace))
        assert len(launches) == 1


def test_resumed_log_prefix_survives_real_subprocess_writes(
    remote_workspace, monkeypatch
):
    workspace, _ = remote_workspace
    state = json.loads((workspace / "kubernetes.json").read_text())
    (workspace / "k8s-previous.log").write_bytes(b"previous epochs\n")
    original = asyncio.create_subprocess_exec

    async def spawn(*args, **kwargs):
        return await original(
            sys.executable, "-c", "print('new epoch', flush=True)", **kwargs
        )

    monkeypatch.setattr(k8s.asyncio, "create_subprocess_exec", spawn)
    asyncio.run(k8s._logs(state, workspace))
    content = (workspace / "train.log").read_bytes()
    assert content.startswith(b"previous epochs\n")
    assert b"new epoch" in content


def test_pod_entrypoint_packages_real_cli_failure_and_waits_for_collection(
    remote_workspace, monkeypatch
):
    workspace, model = remote_workspace
    pod = workspace / "local-pod"
    args = [
        sys.executable,
        "-m",
        "backend.training.train",
        "--data",
        str(pod / "run/dataset"),
        "--unfreeze-steps",
        "0",
    ]
    k8s._pack_input(workspace, model, args)
    with tarfile.open(workspace / "k8s-input.tar") as archive:
        archive.extractall(pod, filter="data")
    original = subprocess.run
    installs = []

    def run(command, **kwargs):
        if command[1:3] == ["-m", "pip"]:
            installs.append(command)
            return subprocess.CompletedProcess(command, 0)
        return original(command, **kwargs)

    class WaitingForCollection(Exception):
        pass

    def wait(_):
        raise WaitingForCollection

    monkeypatch.setattr(k8s.subprocess, "run", run)
    monkeypatch.setattr(k8s.time, "sleep", wait)
    monkeypatch.setenv("PYTHONIOENCODING", "utf-8")
    with pytest.raises(WaitingForCollection):
        k8s._pod_main(pod)
    assert len(installs) == 2
    assert "--no-deps" in installs[1]
    assert not any("torch" in argument for command in installs for argument in command)
    assert json.loads((pod / "exit.json").read_text()) == {"exit_code": 2}
    with tarfile.open(pod / "output.tar") as archive:
        assert "run/train.log" in archive.getnames()
        assert not any("dataset" in name for name in archive.getnames())
        assert "解冻步数必须为正整数" in archive.extractfile(
            "run/train.log"
        ).read().decode("utf-8")
