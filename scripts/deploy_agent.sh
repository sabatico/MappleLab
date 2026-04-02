#!/bin/bash
# Deploy the TART agent to a Mac node.
# Usage: ./scripts/deploy_agent.sh <mac-node-ip> <ssh-user>
#
# Prerequisites:
#   - SSH key already copied to the node (ssh-copy-id)
#   - Python 3 and pip3 installed on node

set -e

NODE="${1:?Usage: $0 <node-ip> <ssh-user>}"
USER="${2:?Usage: $0 <node-ip> <ssh-user>}"
AGENT_DIR="$HOME/tart_agent"
REGISTRY_URL="${REGISTRY_URL:-192.168.1.100:5001}"

echo "==> Deploying TART agent to ${USER}@${NODE}"

# Copy agent files
rsync -av --delete \
  "$(dirname "$0")/../../../tart_agent/" \
  "${USER}@${NODE}:${AGENT_DIR}/"

# Install dependencies on node
ssh "${USER}@${NODE}" "cd ${AGENT_DIR} && pip3 install -r requirements.txt"

# Create start script on node
ssh "${USER}@${NODE}" "cat > ${AGENT_DIR}/start_agent.sh" << EOF
#!/bin/bash
# Include Homebrew paths so tart is found when running as a service
export PATH="/opt/homebrew/bin:/usr/local/bin:\$PATH"
export AGENT_TOKEN="\$(cat ~/.agent_token 2>/dev/null || echo '')"
export REGISTRY_URL="${REGISTRY_URL}"
export MAX_VMS=2
cd ${AGENT_DIR}
python3 agent.py
EOF

ssh "${USER}@${NODE}" "chmod +x ${AGENT_DIR}/start_agent.sh"

echo ""
echo "Agent deployed to ${USER}@${NODE}."
echo "To start: ssh ${USER}@${NODE} '~/tart_agent/start_agent.sh'"
echo ""
echo "To set the agent token on the node:"
echo "  ssh ${USER}@${NODE} 'echo YOUR_TOKEN > ~/.agent_token'"
