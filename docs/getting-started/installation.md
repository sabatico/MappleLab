# Make run.sh executable
chmod +x /Users/Shared/TART_Manager/run.sh
 
# Create the plist file
sudo tee /Library/LaunchDaemons/com.sabatico.tart-manager.plist > /dev/null << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  http://www.apple.com/DTDs/PropertyList-1.0.dtd>
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.sabatico.tart-manager</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/Shared/TART_Manager/run.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/Shared/TART_Manager</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/var/log/tart-manager.log</string>
    <key>StandardErrorPath</key>
    <string>/var/log/tart-manager.error.log</string>
</dict>
</plist>
EOF
 
# Set correct permissions
sudo chown root:wheel /Library/LaunchDaemons/com.sabatico.tart-manager.plist
sudo chmod 644 /Library/LaunchDaemons/com.sabatico.tart-manager.plist
 
# Load and start the service
sudo launchctl load /Library/LaunchDaemons/com.sabatico.tart-manager.plist
sudo launchctl start com.sabatico.tart-manager
 
# Verify it's running (you should see a PID in the first column)
sudo launchctl list | grep tart-manager