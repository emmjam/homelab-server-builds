#!/bin/bash

# Run on TNAS
pct create 110 local:vztmpl/debian-13-standard_13.6-1_amd64.tar.zst \
  --hostname AI-Ollama \
  --ostype debian \
  --unprivileged 1 \
  --cores 6 \
  --memory 8192 \
  --swap 512 \
  --rootfs local-zfs:20 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --features nesting=1 \
  --onboot 1

pct set 110 -dev0 /dev/dri/renderD128,gid=992,mode=0660

pct start 110

# Verify config
pct config 110
pct exec 110 -- cat /etc/os-release
pct exec 110 -- ls -l /dev/dri

# INSIDEW THE CONTAINER, RUN THE FOLLOWING TO INSTALL OLLAMA AND A MODEL
# to logon: pct enter 110
apt update
apt install -y zstd \
  curl \
  ca-certificates \
  mesa-vulkan-drivers \
  vulkan-tools \
  libvulkan1 \
  pciutils

curl -fsSL https://ollama.com/install.sh | sh

mkdir -p /etc/systemd/system/ollama.service.d

cat > /etc/systemd/system/ollama.service.d/override.conf <<'EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_VULKAN=1"
Environment="OLLAMA_IGPU_ENABLE=1"
EOF

systemctl daemon-reload
systemctl restart ollama

ollama pull qwen3:4b

ollama --version
systemctl status ollama --no-pager
