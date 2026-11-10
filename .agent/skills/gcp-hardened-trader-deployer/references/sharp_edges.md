# GCP Deployment Sharp Edges & Traps

## 1. The Private GitHub `curl | bash` 404 Trap
* **Symptom**: User runs `curl -sSL https://raw.githubusercontent.com/.../script.sh | bash` in Cloud Shell and gets:
  `bash: line 1: 404:: command not found`.
* **Cause**: If the repository is Private, GitHub returns `404: Not Found` to unauthenticated requests. Piped into bash, bash executes the string `404:: command not found`.
* **Resolution**:
  - Make repo public (confirming the danger zone confirmation prompt), OR
  - In Cloud Shell, use `git clone https://github.com/...` with personal access token, OR
  - Provide a standalone script that does not curl from raw github.

## 2. Python `MemoryDenyWriteExecute=true` Crash
* **Symptom**: Systemd daemon crashes with `SIGSEGV` or `PermissionError` during Web3/cryptography initialization.
* **Cause**: `cryptography` and `eth-abi` rely on `cffi` which creates executable memory pages. Setting `MemoryDenyWriteExecute=true` prevents this.
* **Resolution**: Set `MemoryDenyWriteExecute=false` in `tradingbot.service`.

## 3. Ephemeral Cloud Shell vs Persistent VM
* **Trap**: Running background tasks directly in Cloud Shell.
* **Reality**: Google Cloud Shell terminates after 20 minutes of inactivity and during browser closures. Always deploy to a Compute Engine VM for true 24/7 autonomous execution.
