# Prerequisites

Complete every section below before starting the installation guide.

---

## What You Need — At a Glance

| Requirement | Where it lives |
|---|---|
| Python 3.10 or later | Manager Mac |
| Homebrew | Manager Mac |
| Docker CLI + Colima | Manager Mac |
| SSH key (manager → nodes) | Manager Mac |
| TART installed | Each node Mac |

---

## 1. Install Homebrew (if not already installed)

Open **Terminal** on the manager Mac and run:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Follow the on-screen prompts. When it finishes, run:

```bash
brew --version
```

You should see a version number. If the command is not found, follow Homebrew's post-install instructions to add it to your PATH.

OPTIONAL 
```bash
echo >> /Users/admin/.zprofile
echo 'eval "$(/opt/homebrew/bin/brew shellenv zsh)"' >> /Users/admin/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv zsh)"
```




---

## 2. Install Python 3.10+

```bash
brew install python@3.12
```

Verify:

```bash
python3 --version
```

Expected output: `Python 3.12.x` (or 3.10+).
IF the version is different, perform this:
Open your shell configuration file (e.g., ~/.zshrc if you are using Zsh, which is the macOS default, or ~/.bash_profile if you are using Bash) using a text editor like nano:
bash
nano ~/.zshrc
# or nano ~/.bash_profile
Add the Homebrew Python libexec/bin directory to the beginning of your PATH. This ensures Homebrew's symlinks are found before the system's Python.Add the following line to the top of the file:
bash
export PATH="/opt/homebrew/opt/python@3.12/libexec/bin:$PATH"
Note: The path /opt/homebrew/opt/python@3.12/libexec/bin is where Homebrew installs unversioned symlinks like python3 pointing to python3.12.
Save the file and exit the editor.
In nano, press Ctrl + O to save, then Enter to confirm the filename, and Ctrl + X to exit.
Reload your shell configuration to apply the changes in your current terminal session:
bash
source ~/.zshrc
# or source ~/.bash_profile
Verify the change by checking the Python version again:
bash
which python3
python3 --version




---

## 3. Install Docker and Colima (MANAGER ONLY)

Colima is a lightweight Docker engine for macOS. The Docker CLI talks to it.

```bash
brew install docker colima
```

Start Colima and set it to start automatically at login:

```bash
colima start
brew services start colima
```

Verify Docker is working:

```bash
docker ps
```

Expected output: an empty table with headers. No errors.

---

## 4. Install TART on Each Node Mac (NODE ONLY)

On **each node Mac**, open Terminal and run:

```bash
brew install cirruslabs/cli/tart
```

Verify:

```bash
tart --version
```

---

## 5. Set Up SSH Key on Manager

This lets the manager Mac connect to node Macs without a password prompt.

### 5a. Generate the key

Run this on the **manager Mac**. Replace `/Users/admin` with your actual home directory if different.

```bash
ssh-keygen -t ed25519 -f /Users/admin/.ssh/id_ed25519 -N ""
```

This creates two files:
- `/Users/admin/.ssh/id_ed25519` — private key (never share this)
- `/Users/admin/.ssh/id_ed25519.pub` — public key (safe to copy to nodes)

### 5b. Authorise the key on each node

Run this once for every node Mac. Replace `admin` with the SSH username on that node and `192.168.1.196` with the node's IP address.

```bash
ssh-copy-id -i /Users/admin/.ssh/id_ed25519.pub admin@192.168.1.196
```

When prompted, enter the node's login password.

### 5c. Test the connection

```bash
ssh -i /Users/admin/.ssh/id_ed25519 admin@192.168.1.196 echo "Connection OK"
```

Expected output: `Connection OK`. If it prompts for a password, the key was not authorised correctly — repeat 5b.

---

## 6. Increase File Descriptor Limits

macOS has a low default limit on how many files and network connections a process can keep open. Increase it on the manager Mac (and optionally on nodes) to prevent resource exhaustion during heavy VM operations.

### 6a. Create the configuration file

Open Terminal and run:

```bash
sudo nano /Library/LaunchDaemons/limit.maxfiles.plist
```

You will be prompted for your password. Enter it.

### 6b. Paste this exact content into the editor

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>limit.maxfiles</string>
    <key>ProgramArguments</key>
    <array>
      <string>launchctl</string>
      <string>limit</string>
      <string>maxfiles</string>
      <string>65536</string>
      <string>200000</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
  </dict>
</plist>
```

Save with **Control + O**, then press Enter. Exit with **Control + X**.

### 6c. Set correct ownership and permissions

```bash
sudo chown root:wheel /Library/LaunchDaemons/limit.maxfiles.plist
sudo chmod 644 /Library/LaunchDaemons/limit.maxfiles.plist
```

### 6d. Load the configuration

```bash
sudo launchctl load -w /Library/LaunchDaemons/limit.maxfiles.plist
```

### 6e. Reboot the Mac

```bash
sudo reboot
```

After the Mac comes back up, verify the new limits:

```bash
launchctl limit maxfiles
```

Expected output shows values at or near `65536 200000`.

> **Note:** If you manage your Macs with MDM or a configuration profile, apply the file limit policy through your existing tooling instead.

---

## 7. Prepare Configuration Values

Before installing MAppleLab, collect the following values:

| Value | What it is | Example |
|---|---|---|
| `SECRET_KEY` | Random string for session signing | `openssl rand -hex 32` |
| `AGENT_TOKEN` | Shared secret between manager and nodes | `openssl rand -hex 24` |
| `REGISTRY_URL` | Manager IP + registry port | `http://192.168.1.195:5001/v2/` |
| `VNC_DIRECT_PORT_MIN/MAX` | Native `.vncloc` TCP proxy range on manager | `57000` / `57099` |
| Node IPs | IP address of each node Mac | `192.168.1.196` |
| SSH user | Login name on each node | `admin` |
| SSH key path | Full path to private key on manager | `/Users/admin/.ssh/id_ed25519` |

Generate a secure `SECRET_KEY`:

```bash
openssl rand -hex 32
```

Generate a secure `AGENT_TOKEN`:

```bash
openssl rand -hex 24
```

Save these values somewhere safe — you will need them in the next step.

## 8. Native `.vncloc` Network Prerequisite (Optional)

If users will use native macOS Screen Sharing via **Download .vncloc**, allow inbound raw TCP to the manager for the configured direct VNC proxy range:

- default: `57000-57099`
- config keys: `VNC_DIRECT_PORT_MIN`, `VNC_DIRECT_PORT_MAX`

This is not HTTP/WebSocket traffic, so standard reverse-proxy `location` rules alone are not enough.

## 9. Usage Analytics Prerequisite

No extra infra prerequisites are required for admin usage analytics beyond a healthy manager database.
Telemetry is captured by manager routes and websocket bridge flows.

---

## Ready

Once all sections above are complete, continue to [Installation](installation.md).
