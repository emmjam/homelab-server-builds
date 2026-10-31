set +x
set -eu
cd /opt/homelab-server-builds

askpass=$(mktemp)
trap 'rm -f "$askpass"' EXIT
cat > "$askpass" <<'EOF'
#!/bin/sh
case "$1" in
  *Username*) printf '%s\n' 'x-access-token' ;;
  *Password*) printf '%s\n' "$RD_OPTION_GITHUB_TOKEN" ;;
  *) exit 1 ;;
esac
EOF
chmod 700 "$askpass"

GIT_ASKPASS="$askpass" GIT_TERMINAL_PROMPT=0 \
  git pull --ff-only origin main
