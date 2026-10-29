
#!/usr/bin/env bash
set -Eeuo pipefail

# install-ai-model.sh
# Installs Ollama and a selected model on an existing Debian VM.
# Does not provision or modify VMs.
# Ollama API remains bound to localhost.

DEFAULT_MODEL="qwen3:4b"
MODEL="$DEFAULT_MODEL"
BIND_ADDRESS="127.0.0.1:11434"
INSTALL_URL="https://ollama.com/install.sh"

usage() {
    cat <<'EOF'
Usage:
  install-ai-model.sh [options]

Options:
  --model NAME       Ollama model to install (default: qwen3:4b)
  --help             Show this help

Examples:
  ./install-ai-model.sh
  ./install-ai-model.sh --model qwen3:4b
  ./install-ai-model.sh --model gemma3:4b
EOF
}

while (($#)); do
    case "$1" in
        --model)
            [[ $# -ge 2 && -n "$2" ]] || {
                echo "ERROR: --model requires a value." >&2
                exit 2
            }
            MODEL="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: Run this script as root, e.g. sudo ./install-ai-model.sh" >&2
    exit 1
fi

if [[ ! -f /etc/debian_version ]]; then
    echo "ERROR: This installer is intended for Debian." >&2
    exit 1
fi

echo "==> Installing prerequisites"
apt-get update
apt-get install -y ca-certificates curl

for command in curl systemctl; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "ERROR: Required command '$command' is missing." >&2
        exit 1
    fi
done

if ! command -v ollama >/dev/null 2>&1; then
    echo "==> Installing Ollama"
    curl -fsSL "$INSTALL_URL" | sh
else
    echo "==> Ollama is already installed; reusing existing installation"
fi

if ! command -v ollama >/dev/null 2>&1; then
    echo "ERROR: Ollama executable was not found after installation." >&2
    exit 1
fi

echo "==> Configuring Ollama API for localhost only"
install -d -m 0755 /etc/systemd/system/ollama.service.d

cat > /etc/systemd/system/ollama.service.d/10-local-only.conf <<EOF
[Service]
Environment="OLLAMA_HOST=$BIND_ADDRESS"
EOF

systemctl daemon-reload
systemctl enable ollama.service
systemctl restart ollama.service

echo "==> Waiting for Ollama API"
ready=0
for _ in $(seq 1 30); do
    if curl --silent --fail \
        http://127.0.0.1:11434/api/tags >/dev/null; then
        ready=1
        break
    fi
    sleep 2
done

if [[ "$ready" -ne 1 ]]; then
    echo "ERROR: Ollama API did not become ready." >&2
    systemctl --no-pager --full status ollama.service || true
    journalctl -u ollama.service -n 50 --no-pager || true
    exit 1
fi

echo "==> Checking model: $MODEL"
if ! ollama list | awk 'NR > 1 {print $1}' | grep -Fxq -- "$MODEL"; then
    echo "==> Downloading model: $MODEL"
    ollama pull "$MODEL"
else
    echo "==> Model already present; skipping download"
fi

echo "==> Running inference test"
RESPONSE=$(curl --silent --show-error --fail \
    --max-time 300 \
    http://127.0.0.1:11434/api/chat \
    -H 'Content-Type: application/json' \
    -d "$(MODEL="$MODEL" python3 -c '
import json, os
print(json.dumps({
    "model": os.environ["MODEL"],
    "messages": [{"role": "user", "content": "Reply with exactly: AI model ready"}],
    "stream": False
}))
')" ) || {
    echo "ERROR: Inference test failed." >&2
    exit 1
}

if ! printf '%s' "$RESPONSE" | python3 -c '
import json, sys
data = json.load(sys.stdin)
message = data.get("message", {}).get("content", "")
if not message.strip():
    sys.exit(1)
print(message)
'; then
    echo "ERROR: Ollama returned no usable response." >&2
    exit 1
fi

echo
echo "==> Verifying listener"
ss -lnt | grep -F '127.0.0.1:11434' || {
    echo "ERROR: Expected localhost listener was not found." >&2
    ss -lnt | grep '11434' || true
    exit 1
}

echo
echo "SUCCESS"
echo "Model: $MODEL"
echo "API:   http://127.0.0.1:11434"
echo "Service: ollama.service"
echo
echo "Useful commands:"
echo "  ollama list"
echo "  ollama run $MODEL"
echo "  journalctl -u ollama -f"
