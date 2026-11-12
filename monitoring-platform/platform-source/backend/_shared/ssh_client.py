"""SSH client for remote server operations."""
import subprocess, os, stat, tempfile


class SSHClient:
    def __init__(self, host, port, user, key_path=None, password=None):
        self.host = host
        self.port = port
        self.user = user
        self.key_path = key_path
        self.password = password
        self._askpass_path = None

    def _askpass_env(self):
        """Env that feeds the password to ssh/scp without sshpass (OpenSSH >= 8.4)."""
        if not self.password:
            return None
        if self._askpass_path is None:
            fd, path = tempfile.mkstemp(prefix="igem-askpass-")
            with os.fdopen(fd, "w") as f:
                f.write("#!/bin/sh\nprintf '%s\\n' '")
                f.write(self.password.replace("'", "'\\''"))
                f.write("'\n")
            os.chmod(path, stat.S_IRUSR | stat.S_IXUSR)
            self._askpass_path = path
        return {
            "SSH_ASKPASS": self._askpass_path,
            "SSH_ASKPASS_REQUIRE": "force",
            "DISPLAY": ":0",
        }

    def _ssh_base(self):
        base = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10",
                "-p", str(self.port)]
        if self.key_path:
            base += ["-i", os.path.expanduser(self.key_path)]
        return base

    def _scp_base(self):
        base = ["scp", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10",
                "-P", str(self.port)]
        if self.key_path:
            base += ["-i", os.path.expanduser(self.key_path)]
        return base

    @property
    def _remote_dest(self):
        return f"{self.user}@{self.host}"

    def _run(self, cmd, timeout):
        env = self._askpass_env()
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                               env=env, stdin=subprocess.DEVNULL if env else None)
            return r
        except subprocess.TimeoutExpired:
            return None
        except Exception:
            return None

    def exec(self, command, timeout=30):
        """Run a command on the remote server, return (stdout, stderr, exit_code)."""
        cmd = self._ssh_base() + [self._remote_dest, command]
        r = self._run(cmd, timeout)
        if r is None:
            return "", "TIMEOUT", -1
        return r.stdout, r.stderr, r.returncode

    def upload(self, local_path, remote_path, timeout=60):
        """Upload a file or directory to the remote server."""
        cmd = self._scp_base() + ["-r", local_path, f"{self._remote_dest}:{remote_path}"]
        r = self._run(cmd, timeout)
        if r is None:
            return False
        return r.returncode == 0

    def download(self, remote_path, local_path, timeout=120):
        """Download a file or directory from the remote server."""
        cmd = self._scp_base() + ["-r", f"{self._remote_dest}:{remote_path}", local_path]
        r = self._run(cmd, timeout)
        if r is None:
            return False
        return r.returncode == 0

    def download_stream(self, command, local_path, timeout=600):
        """Stream a remote command's stdout (binary) into local_path."""
        cmd = self._ssh_base() + ["-T", self._remote_dest, command]
        env = self._askpass_env()
        try:
            with open(local_path, "wb") as f:
                r = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE,
                                   timeout=timeout, env=env,
                                   stdin=subprocess.DEVNULL if env else None)
            return r.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return False

    def upload_bytes(self, content, remote_path, timeout=30):
        """Upload string content as a file using SSH cat."""
        cmd = f"cat > {remote_path} << 'ENDOFFILE'\n{content}\nENDOFFILE"
        return self.exec(cmd, timeout=timeout)

    def file_exists(self, remote_path):
        """Check if a file exists on the remote."""
        out, _, code = self.exec(f"test -f {remote_path} && echo YES || echo NO")
        return "YES" in out

    def list_files(self, remote_pattern):
        """List files matching a pattern on the remote."""
        out, _, code = self.exec(f"ls {remote_pattern} 2>/dev/null || true")
        return [f for f in out.strip().split("\n") if f]
