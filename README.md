# Windows Monitor

Comprehensive real-time Windows system monitoring with rolling log display.

Windows Monitor is a powerful, all-in-one monitoring solution for Windows 10/11 that captures over 100 different event types in real time. Whether you are a system administrator, security analyst, developer, incident responder, or power user, Windows Monitor gives you deep visibility into what is happening on your machine — from process creation and network connections to registry changes, hardware status, security events, and much more.

Designed for continuous operation, Windows Monitor provides a rolling log display that always shows the newest events, supports rich event details, multiple view modes, bookmarks, highlights, regex search, and automatic log rotation with 30-day cleanup. It can run in a terminal, log to dated folders, start automatically on boot, and even be compiled into a standalone executable.

---

## Why Windows Monitor?

Windows is a complex operating system with thousands of moving parts. Processes start and stop, services change state, network connections open and close, registry keys are modified, drivers load and unload, USB devices connect and disconnect, and security events fire constantly. Most users never see any of this. Windows Monitor changes that.

With Windows Monitor you can:

- **See everything in real time** — Watch processes, network connections, services, registry changes, and hardware events as they happen.
- **Investigate security incidents** — Detect suspicious processes, failed logins, autorun entries, Defender exclusions, and persistence mechanisms.
- **Troubleshoot system issues** — Track service failures, driver problems, disk health, thermal events, and Windows Update activity.
- **Audit system changes** — Monitor registry modifications, Group Policy changes, firewall rules, scheduled tasks, and installed software.
- **Understand process behavior** — Visualize parent-child relationships and see exactly which command lines were executed.
- **Monitor hardware health** — Track CPU/GPU temperature, fan speed, battery status, disk SMART data, and thermal zones.
- **Keep long-term logs** — Organize logs by date and time, with automatic 30-day cleanup.
- **Export and analyze** — Export events to JSON or CSV for further processing.

Windows Monitor is built for people who need to know what is really happening on their systems.

---

## Features

### 100+ Built-in Monitors

Windows Monitor ships with more than 100 specialized monitors organized into logical categories. Each monitor runs independently and can be enabled or disabled on demand. Every monitor produces structured events with timestamps, severity levels, categories, and detailed data fields.

#### System Monitoring
- **DNS** — Real DNS queries with IP resolution
- **PROCESS** — Process start/end with full command lines
- **PROCESS_TREE** — Process parent-child relationships
- **NETWORK** — Connections, traffic, ARP table
- **SYSTEM** — CPU, RAM, Swap, Disk usage
- **CPU_CORE** — Per-core CPU usage
- **BANDWIDTH** — Network bandwidth usage
- **PROC_RES** — Top resource-consuming processes

#### Windows Services
- **SERVICE** — Windows service state changes
- **SERVICE_DETAIL** — Detailed service monitoring
- **FIREWALL** — Firewall packet events
- **FW_RULES** — Firewall rule changes

#### Event Logging
- **EVENTLOG** — Windows Event Log entries
- **EVENTLOG_CH** — Event log channels
- **WEF** — Windows Event Forwarding
- **WER** — Windows Error Reporting
- **WER_DETAIL** — Detailed WER reports

#### Security
- **DEFENDER** — Windows Defender status
- **DEF_EXCL** — Defender exclusions
- **DEF_SCAN** — Defender scans
- **DEF_BEHAV** — Defender behavior events
- **DEF_ATP** — Defender ATP alerts
- **THREAT** — Suspicious process detection
- **UAC** — UAC settings changes
- **SMARTSCREEN** — SmartScreen status
- **HELLO** — Windows Hello / BitLocker
- **TPM_BL** — TPM / BitLocker events
- **LAPS** — LAPS password changes
- **CRED** — Credential manager events
- **AUTORUN** — Autorun entries
- **APPLOCKER** — AppLocker events
- **APPCOMPAT** — Application compatibility
- **SECURITY** — Failed login attempts

#### Registry & Configuration
- **REGISTRY** — Registry changes
- **WMI** — WMI events
- **HOSTS** — Hosts file changes
- **PROXY** — Proxy settings
- **AUTOPILOT** — Autopilot status
- **GP** — Group Policy changes
- **BOOT** — Boot configuration
- **TZ** — Timezone changes

#### Hardware
- **DEVICE** — USB device changes
- **USB_DETAIL** — Detailed USB devices
- **DRIVER** — Driver load/unload
- **BATTERY** — Battery status and charge
- **TEMP** — CPU/GPU temperature
- **DISK_HEALTH** — Disk SMART status
- **FAN** — Fan speed
- **THERMAL** — Thermal zones
- **GPU** — GPU information
- **DISPLAY** — Display settings
- **AUDIO** — Audio devices
- **BT** — Bluetooth devices
- **PRINTER** — Printer queue

#### Network
- **LAN** — LAN device discovery
- **WIFI** — WiFi network profiles
- **SHARE** — Network share changes
- **NETADAPTER** — Network adapters
- **TCPSTATS** — TCP statistics
- **NET_CONN** — New network connections
- **NETPROF** — Network profiles
- **DNS_CACHE** — DNS cache
- **PORT** — Port monitoring
- **WEB** — Website availability

#### Files & Applications
- **FILE** — File changes
- **DIR** — Directory changes
- **APPLICATION** — Application log changes
- **RECENT** — Recent documents
- **JUMPLIST** — Jump lists
- **TYPEDURL** — Typed URLs
- **USERASSIST** — User assist
- **BAGMRU** — Bag MRU
- **PREFETCH** — Prefetch files
- **AMCACHE** — Amcache
- **LOGTAIL** — Log file tailing

#### Windows Features
- **WUPDATE** — Windows updates
- **WU_LOG** — Windows Update log
- **WU_TELE** — Update telemetry
- **FEATUPDATE** — Feature updates
- **SOFTWARE** — Installed software
- **WINFEAT** — Windows features
- **STORE_APPS** — Store apps
- **RECOVERY** — Recovery status
- **SANDBOX** — Windows Sandbox
- **WSL** — WSL distros
- **DOCKER** — Docker containers
- **HYPERV** — Hyper-V VMs
- **IIS** — IIS websites
- **SQL** — SQL Server services
- **EXCHANGE** — Exchange services
- **AD** — Active Directory events

#### Advanced
- **POWERSHELL** — PowerShell execution
- **WINRM** — WinRM events
- **SYSMON** — Sysmon events
- **SCHED_TASK** — Scheduled tasks
- **TASK_EXEC** — Task execution
- **CLOUD** — Cloud sync (OneDrive, Dropbox, Google Drive)
- **WAC** — Windows Admin Center
- **WPR** — Windows Performance Recorder
- **MEMDIAG** — Memory diagnostic
- **RESET** — Windows Reset
- **CRYPTO** — Crypto keys
- **CERT** — Certificates
- **SETUPAPI** — SetupAPI log
- **PERFMON** — Performance counters

---

## Detailed Monitor Descriptions

### System Monitoring

**DNS** — Captures real DNS queries made by the system, including the queried domain name and the resolved IP address. Useful for detecting DNS hijacking, tracking domain access, and troubleshooting name resolution issues.

**PROCESS** — Monitors process creation and termination. Includes full command line, process ID, parent process ID, user context, and start time. Essential for detecting suspicious executions and understanding what runs on your system.

**PROCESS_TREE** — Builds a parent-child relationship map of processes. Helps you understand which process spawned which, making it easier to trace malicious chains or debug application behavior.

**NETWORK** — Tracks network connections, traffic volumes, and the ARP table. Shows which processes are communicating with which remote endpoints.

**SYSTEM** — Monitors overall CPU, RAM, swap, and disk usage. Provides a baseline for system health and helps detect resource exhaustion.

**CPU_CORE** — Per-core CPU usage monitoring. Useful for detecting single-threaded bottlenecks and uneven load distribution.

**BANDWIDTH** — Tracks network bandwidth usage per interface. Helps identify bandwidth hogs and unusual traffic patterns.

**PROC_RES** — Lists the top resource-consuming processes by CPU and memory. Useful for quick identification of performance problems.

### Windows Services

**SERVICE** — Detects Windows service state changes: started, stopped, paused, continued. Unexpected service changes can indicate tampering or failures.

**SERVICE_DETAIL** — Provides deeper detail about service configuration changes, including start type and binary path modifications.

**FIREWALL** — Captures firewall packet events, including allowed and blocked connections. Useful for network security analysis.

**FW_RULES** — Monitors changes to Windows Firewall rules. Detects new rules, deleted rules, and modified rules that could weaken security.

### Event Logging

**EVENTLOG** — Reads Windows Event Log entries across multiple channels. Central source for system, application, and security events.

**EVENTLOG_CH** — Monitors event log channel configuration and state changes.

**WEF** — Tracks Windows Event Forwarding activity, useful in enterprise environments with centralized logging.

**WER** — Captures Windows Error Reporting events, including application crashes and hangs.

**WER_DETAIL** — Provides detailed WER reports with faulting module, exception code, and stack information.

### Security

**DEFENDER** — Monitors Windows Defender status, including real-time protection state, signature versions, and scan results.

**DEF_EXCL** — Detects changes to Defender exclusions. Attackers often add exclusions to hide malware.

**DEF_SCAN** — Tracks Defender scan activity, including quick scans, full scans, and custom scans.

**DEF_BEHAV** — Captures Defender behavior monitoring events, including suspicious process behavior.

**DEF_ATP** — Monitors Defender Advanced Threat Protection alerts and detections.

**THREAT** — Detects suspicious processes based on heuristics and known indicators.

**UAC** — Monitors User Account Control settings changes. Lowering UAC can weaken system security.

**SMARTSCREEN** — Tracks SmartScreen status and reputation check results.

**HELLO** — Monitors Windows Hello and BitLocker status changes.

**TPM_BL** — Tracks TPM and BitLocker events, including encryption state changes.

**LAPS** — Monitors Local Administrator Password Solution (LAPS) password changes.

**CRED** — Captures Credential Manager events, including credential access and modification.

**AUTORUN** — Monitors autorun entries in the registry and startup folders. Key for detecting persistence.

**APPLOCKER** — Captures AppLocker events, including allowed and blocked application executions.

**APPCOMPAT** — Tracks application compatibility events, including shim usage.

**SECURITY** — Monitors failed login attempts and other security-relevant events.

### Registry & Configuration

**REGISTRY** — Monitors registry key and value changes. Critical for detecting configuration tampering and persistence.

**WMI** — Captures WMI events, including permanent event subscriptions often used by attackers.

**HOSTS** — Detects changes to the hosts file. A common technique for DNS hijacking.

**PROXY** — Monitors proxy settings changes. Malware sometimes redirects traffic through a proxy.

**AUTOPILOT** — Tracks Windows Autopilot status and provisioning events.

**GP** — Monitors Group Policy changes, including policy application and refresh events.

**BOOT** — Tracks boot configuration changes, including BCD modifications.

**TZ** — Monitors timezone changes, which can affect log correlation and scheduling.

### Hardware

**DEVICE** — Detects USB and other device connection/disconnection events.

**USB_DETAIL** — Provides detailed USB device information, including VID, PID, and serial number.

**DRIVER** — Monitors driver load and unload events. Suspicious drivers can indicate rootkits or hardware issues.

**BATTERY** — Tracks battery status, charge level, and power source changes.

**TEMP** — Monitors CPU and GPU temperature. Helps detect overheating and cooling problems.

**DISK_HEALTH** — Reads disk SMART data to predict drive failures.

**FAN** — Monitors fan speed. Useful for detecting cooling issues.

**THERMAL** — Tracks thermal zone temperatures across the system.

**GPU** — Captures GPU information, including model, driver version, and usage.

**DISPLAY** — Monitors display setting changes, including resolution and layout.

**AUDIO** — Tracks audio device changes, including default device switches.

**BT** — Monitors Bluetooth device connections and disconnections.

**PRINTER** — Tracks printer queue activity and printer changes.

### Network

**LAN** — Discovers devices on the local network.

**WIFI** — Monitors WiFi network profiles, including saved networks and connection events.

**SHARE** — Detects network share creation, modification, and deletion.

**NETADAPTER** — Monitors network adapter changes, including enable/disable and IP changes.

**TCPSTATS** — Captures TCP statistics, including retransmissions and connection failures.

**NET_CONN** — Detects new network connections as they are established.

**NETPROF** — Monitors network profile changes, including public/private network switching.

**DNS_CACHE** — Tracks DNS cache entries and changes.

**PORT** — Monitors port activity, including listening ports and new bindings.

**WEB** — Checks website availability and response times.

### Files & Applications

**FILE** — Monitors file changes, including creation, modification, and deletion.

**DIR** — Tracks directory changes, including new files and subdirectories.

**APPLICATION** — Captures application log changes.

**RECENT** — Monitors recent documents and files accessed.

**JUMPLIST** — Tracks jump list entries, which reveal recently used files per application.

**TYPEDURL** — Monitors typed URLs in browsers.

**USERASSIST** — Captures UserAssist data, which tracks GUI program usage.

**BAGMRU** — Monitors Bag MRU data, which tracks folder view settings.

**PREFETCH** — Tracks prefetch files, which indicate program execution.

**AMCACHE** — Monitors Amcache data, which records execution artifacts.

**LOGTAIL** — Tails any log file in real time, useful for custom logs.

### Windows Features

**WUPDATE** — Monitors Windows Update activity, including update installation and failures.

**WU_LOG** — Parses the Windows Update log for detailed update information.

**WU_TELE** — Tracks Windows Update telemetry events.

**FEATUPDATE** — Monitors feature updates, including major Windows version upgrades.

**SOFTWARE** — Tracks installed software changes.

**WINFEAT** — Monitors Windows feature installation and removal.

**STORE_APPS** — Tracks Microsoft Store app installation and updates.

**RECOVERY** — Monitors system recovery status and events.

**SANDBOX** — Tracks Windows Sandbox activity.

**WSL** — Monitors Windows Subsystem for Linux distros and activity.

**DOCKER** — Tracks Docker container lifecycle events.

**HYPERV** — Monitors Hyper-V virtual machine events.

**IIS** — Tracks IIS website and application pool events.

**SQL** — Monitors SQL Server service events.

**EXCHANGE** — Tracks Exchange service events.

**AD** — Monitors Active Directory events, including authentication and directory changes.

### Advanced

**POWERSHELL** — Captures PowerShell script block logging and execution events.

**WINRM** — Monitors WinRM remote management events.

**SYSMON** — Consumes Sysmon events for advanced endpoint monitoring.

**SCHED_TASK** — Monitors scheduled task creation, modification, and deletion.

**TASK_EXEC** — Tracks scheduled task execution events.

**CLOUD** — Monitors cloud sync clients: OneDrive, Dropbox, Google Drive.

**WAC** — Tracks Windows Admin Center management events.

**WPR** — Monitors Windows Performance Recorder traces.

**MEMDIAG** — Captures memory diagnostic events.

**RESET** — Tracks Windows Reset activity.

**CRYPTO** — Monitors cryptographic key usage and changes.

**CERT** — Tracks certificate installation, removal, and changes.

**SETUPAPI** — Parses SetupAPI logs for driver and device installation events.

**PERFMON** — Monitors performance counters for deep system metrics.

---

## Rich Event Details

Every event captured by Windows Monitor includes:

- Timestamp with millisecond precision
- Source monitor name
- Event category
- Severity level (DEBUG / INFO / NOTICE / WARNING / ERROR / CRITICAL)
- Detailed message
- Structured data fields with location information
- Bookmark and highlight support
- Process ID, parent process ID, and user context where available
- File paths, registry keys, network endpoints, and device identifiers
- Human-readable summary plus machine-parsable fields

Events are designed to be both easy to read in a terminal and easy to export for further analysis.

---

## Multiple View Modes

- **Normal** — Standard scrolling log with full event details
- **Dashboard** — Statistics overview with counters and summaries
- **Alerts** — Filtered warnings and errors only
- **Tree** — Process tree view showing parent-child relationships
- **Compact** — Condensed one-line format for high-volume monitoring

Switch between modes at any time without losing your place.

---

## Advanced Features

- **Dated Folder Logging** — Organize logs by date and time
- **30-Day Auto-Cleanup** — Automatic log rotation and cleanup
- **Auto-Start** — Add to Windows startup
- **EXE Build** — Compile to standalone executable
- **Sound Alerts** — Audio alerts for warnings and errors
- **Event Export** — Export to JSON / CSV
- **Full-Screen Display** — No gaps, continuous scrolling
- **Slow Mode** — Comfortable reading speed
- **Event Deduplication** — 5-second window to reduce noise
- **Regex Search** — Advanced text filtering
- **Source Filtering** — Filter by monitor source
- **Bookmarks** — Mark important events
- **Highlights** — Highlight specific sources
- **Configurable Intervals** — Control how often each monitor polls
- **Per-Monitor Toggle** — Enable or disable any monitor
- **Structured Log Files** — One log file per monitor per session
- **JSON Configuration** — Simple, human-readable config file
- **Real-Time Rolling Display** — Always shows the newest events
- **Event Severity Filtering** — Focus on what matters
- **Process Tree Visualization** — Understand parent-child relationships
- **Network Connection Tracking** — See every new connection
- **Security Event Correlation** — Spot suspicious activity faster
- **Hardware Health Monitoring** — Temperature, battery, disk health
- **Windows Update Tracking** — Know when updates happen
- **Service State Monitoring** — Detect unexpected service changes
- **Registry Change Detection** — Catch unauthorized modifications
- **File System Monitoring** — Track file and directory changes
- **Scheduled Task Monitoring** — See what runs and when
- **PowerShell Execution Logging** — Audit script activity
- **Sysmon Integration** — Consume Sysmon events directly
- **Cloud Sync Monitoring** — Track OneDrive, Dropbox, Google Drive
- **Virtualization Support** — WSL, Docker, Hyper-V, Sandbox
- **Server Role Monitoring** — IIS, SQL, Exchange, AD
- **Certificate Monitoring** — Track certificate changes
- **Crypto Key Monitoring** — Detect key usage
- **Performance Counter Monitoring** — Deep system metrics
- **Memory Diagnostic Events** — Catch hardware memory issues
- **Boot Configuration Changes** — Detect boot tampering
- **Timezone Changes** — Track system time changes
- **Group Policy Changes** — Monitor policy updates
- **Proxy Setting Changes** — Detect network redirection
- **Hosts File Monitoring** — Catch DNS hijacking
- **USB Device Tracking** — See every device connect
- **Driver Load/Unload Events** — Spot suspicious drivers
- **Printer Queue Monitoring** — Track print jobs
- **Bluetooth Device Monitoring** — See nearby devices
- **Display Setting Changes** — Track resolution and layout
- **Audio Device Changes** — Monitor sound devices
- **Battery Health Tracking** — Know your battery status
- **Thermal Zone Monitoring** — Prevent overheating
- **Fan Speed Monitoring** — Detect cooling issues
- **GPU Monitoring** — Track GPU usage and status
- **SMART Disk Health** — Predict drive failures
- **Windows Hello / BitLocker** — Monitor security features
- **LAPS Password Changes** — Track local admin passwords
- **Credential Manager Events** — Detect credential access
- **Autorun Entry Monitoring** — Catch persistence attempts
- **AppLocker Events** — Monitor application control
- **AppCompat Events** — Track compatibility issues
- **SmartScreen Status** — Monitor reputation checks
- **UAC Setting Changes** — Detect privilege changes
- **Defender ATP Alerts** — Advanced threat protection
- **Defender Behavior Events** — Catch suspicious behavior
- **Defender Scan Results** — Track scan activity
- **Defender Exclusions** — Detect exclusion changes
- **Threat Detection** — Identify suspicious processes
- **Failed Login Tracking** — Detect brute force attempts
- **Event Log Channels** — Monitor all channels
- **Windows Error Reporting** — Catch application crashes
- **Windows Event Forwarding** — Centralized log collection
- **Active Directory Events** — Monitor domain activity
- **Exchange Service Monitoring** — Track mail server health
- **SQL Server Monitoring** — Track database services
- **IIS Website Monitoring** — Track web server status
- **Hyper-V VM Monitoring** — Track virtual machines
- **Docker Container Monitoring** — Track containers
- **WSL Distro Monitoring** — Track Linux subsystems
- **Windows Sandbox Events** — Monitor isolated environments
- **Recovery Status Monitoring** — Track system recovery
- **Store App Monitoring** — Track UWP apps
- **Windows Feature Changes** — Detect feature installs
- **Installed Software Tracking** — Know what is installed
- **Feature Update Tracking** — Monitor major updates
- **Update Telemetry** — Track update behavior
- **Windows Update Log** — Parse update logs
- **Windows Update Events** — Track update lifecycle
- **Log File Tailing** — Follow any log file
- **Amcache Monitoring** — Track execution artifacts
- **Prefetch Monitoring** — Detect program execution
- **Bag MRU Monitoring** — Track folder views
- **UserAssist Monitoring** — Track GUI program usage
- **Typed URL Monitoring** — Track browser URLs
- **Jump List Monitoring** — Track recent files
- **Recent Document Monitoring** — Track opened files
- **Application Log Monitoring** — Track app logs
- **Directory Change Monitoring** — Track folder changes
- **File Change Monitoring** — Track file changes
- **Website Availability Monitoring** — Track uptime
- **Port Monitoring** — Detect open ports
- **DNS Cache Monitoring** — Track DNS resolution
- **Network Profile Monitoring** — Track network changes
- **New Connection Monitoring** — Detect new connections
- **TCP Statistics** — Track TCP health
- **Network Adapter Monitoring** — Track adapter changes
- **Network Share Monitoring** — Track shared folders
- **WiFi Profile Monitoring** — Track wireless networks
- **LAN Device Discovery** — Find devices on your network
- **Performance Counter Monitoring** — Deep system metrics
- **SetupAPI Log Monitoring** — Track driver installs
- **Certificate Monitoring** — Track certificate changes
- **Crypto Key Monitoring** — Detect key usage
- **Windows Reset Monitoring** — Track system resets
- **Memory Diagnostic Events** — Catch hardware memory issues
- **Windows Performance Recorder** — Track performance traces
- **Windows Admin Center** — Monitor management events
- **Cloud Sync Monitoring** — Track OneDrive, Dropbox, Google Drive
- **Scheduled Task Monitoring** — See what runs and when
- **Task Execution Monitoring** — Track task runs
- **Sysmon Event Monitoring** — Consume Sysmon events
- **WinRM Event Monitoring** — Track remote management
- **PowerShell Execution Logging** — Audit script activity
- **Active Directory Events** — Monitor domain activity
- **Exchange Service Monitoring** — Track mail server health
- **SQL Server Monitoring** — Track database services
- **IIS Website Monitoring** — Track web server status
- **Hyper-V VM Monitoring** — Track virtual machines
- **Docker Container Monitoring** — Track containers
- **WSL Distro Monitoring** — Track Linux subsystems
- **Windows Sandbox Events** — Monitor isolated environments
- **Recovery Status Monitoring** — Track system recovery
- **Store App Monitoring** — Track UWP apps
- **Windows Feature Changes** — Detect feature installs
- **Installed Software Tracking** — Know what is installed
- **Feature Update Tracking** — Monitor major updates
- **Update Telemetry** — Track update behavior
- **Windows Update Log** — Parse update logs
- **Windows Update Events** — Track update lifecycle
- **Event Deduplication** — Reduce noise with a 5-second window
- **Severity Levels** — DEBUG, INFO, NOTICE, WARNING, ERROR, CRITICAL
- **Structured Data Fields** — Machine-readable event payloads
- **Location Information** — File paths, registry keys, network endpoints
- **Bookmark Support** — Mark and revisit important events
- **Highlight Support** — Visually emphasize specific sources
- **Regex Search** — Powerful text filtering
- **Source Filtering** — Focus on one or more monitors
- **Quick Source Filter** — Fast switching between sources
- **Pause / Resume** — Freeze the display when needed
- **Clear Events** — Reset the view instantly
- **Toggle Data Display** — Show or hide structured fields
- **Compact Mode** — One-line events for high-volume scenarios
- **Export Events** — JSON and CSV output
- **Full-Screen Mode** — No gaps, continuous scrolling
- **Slow Mode** — Comfortable reading speed
- **Sound Alerts** — Audio notifications for warnings and errors
- **Auto-Start** — Launch on Windows boot
- **EXE Build** — Standalone executable with PyInstaller
- **Config File** — JSON-based configuration
- **Per-Monitor Intervals** — Control polling frequency
- **Dated Folder Logging** — Logs organized by date and time
- **30-Day Auto-Cleanup** — Automatic log rotation
- **Structured Log Files** — One file per monitor per session
- **Real-Time Rolling Display** — Always shows the newest events
- **Multi-View Modes** — Normal, Dashboard, Alerts, Tree, Compact
- **Process Tree View** — Parent-child process relationships
- **Network Connection Tracking** — See every new connection
- **Security Event Correlation** — Spot suspicious activity faster
- **Hardware Health Monitoring** — Temperature, battery, disk health
- **Windows Update Tracking** — Know when updates happen
- **Service State Monitoring** — Detect unexpected service changes
- **Registry Change Detection** — Catch unauthorized modifications
- **File System Monitoring** — Track file and directory changes
- **Scheduled Task Monitoring** — See what runs and when
- **PowerShell Execution Logging** — Audit script activity
- **Sysmon Integration** — Consume Sysmon events directly
- **Cloud Sync Monitoring** — Track OneDrive, Dropbox, Google Drive
- **Virtualization Support** — WSL, Docker, Hyper-V, Sandbox
- **Server Role Monitoring** — IIS, SQL, Exchange, AD
- **Certificate Monitoring** — Track certificate changes
- **Crypto Key Monitoring** — Detect key usage
- **Performance Counter Monitoring** — Deep system metrics
- **Memory Diagnostic Events** — Catch hardware memory issues
- **Boot Configuration Changes** — Detect boot tampering
- **Timezone Changes** — Track system time changes
- **Group Policy Changes** — Monitor policy updates
- **Proxy Setting Changes** — Detect network redirection
- **Hosts File Monitoring** — Catch DNS hijacking
- **USB Device Tracking** — See every device connect
- **Driver Load/Unload Events** — Spot suspicious drivers
- **Printer Queue Monitoring** — Track print jobs
- **Bluetooth Device Monitoring** — See nearby devices
- **Display Setting Changes** — Track resolution and layout
- **Audio Device Changes** — Monitor sound devices
- **Battery Health Tracking** — Know your battery status
- **Thermal Zone Monitoring** — Prevent overheating
- **Fan Speed Monitoring** — Detect cooling issues
- **GPU Monitoring** — Track GPU usage and status
- **SMART Disk Health** — Predict drive failures
- **Windows Hello / BitLocker** — Monitor security features
- **LAPS Password Changes** — Track local admin passwords
- **Credential Manager Events** — Detect credential access
- **Autorun Entry Monitoring** — Catch persistence attempts
- **AppLocker Events** — Monitor application control
- **AppCompat Events** — Track compatibility issues
- **SmartScreen Status** — Monitor reputation checks
- **UAC Setting Changes** — Detect privilege changes
- **Defender ATP Alerts** — Advanced threat protection
- **Defender Behavior Events** — Catch suspicious behavior
- **Defender Scan Results** — Track scan activity
- **Defender Exclusions** — Detect exclusion changes
- **Threat Detection** — Identify suspicious processes
- **Failed Login Tracking** — Detect brute force attempts
- **Event Log Channels** — Monitor all channels
- **Windows Error Reporting** — Catch application crashes
- **Windows Event Forwarding** — Centralized log collection
- **Active Directory Events** — Monitor domain activity
- **Exchange Service Monitoring** — Track mail server health
- **SQL Server Monitoring** — Track database services
- **IIS Website Monitoring** — Track web server status
- **Hyper-V VM Monitoring** — Track virtual machines
- **Docker Container Monitoring** — Track containers
- **WSL Distro Monitoring** — Track Linux subsystems
- **Windows Sandbox Events** — Monitor isolated environments
- **Recovery Status Monitoring** — Track system recovery
- **Store App Monitoring** — Track UWP apps
- **Windows Feature Changes** — Detect feature installs
- **Installed Software Tracking** — Know what is installed
- **Feature Update Tracking** — Monitor major updates
- **Update Telemetry** — Track update behavior
- **Windows Update Log** — Parse update logs
- **Windows Update Events** — Track update lifecycle

---

## Use Cases

### Security Analysis
- Detect suspicious process executions
- Monitor persistence mechanisms
- Track failed login attempts
- Watch Defender exclusions and ATP alerts
- Correlate network connections with processes
- Detect registry and hosts file tampering

### System Administration
- Track service state changes
- Monitor Windows Update activity
- Watch driver load/unload events
- Detect hardware failures early
- Monitor disk health and thermal zones
- Audit scheduled tasks and Group Policy changes

### Incident Response
- Reconstruct process trees
- Trace network connections
- Identify autorun entries
- Review PowerShell execution
- Analyze event log channels
- Export events for forensic analysis

### Performance Troubleshooting
- Identify top resource consumers
- Monitor CPU per core
- Track bandwidth usage
- Watch thermal and fan events
- Analyze performance counters
- Detect memory diagnostic events

### Compliance and Auditing
- Log registry changes
- Track installed software
- Monitor certificate changes
- Audit user activity
- Track file and directory changes
- Export structured logs

---

## Controls

- `↑/↓` — Scroll up/down
- `PgUp/PgDn` — Page scroll
- `Home/End` — Jump to newest/oldest
- `Enter` — View event detail
- `Space` — Pause/resume
- `C` — Clear events
- `D` — Toggle data display
- `M` — Toggle compact mode
- `B` — Bookmark event
- `A` — Toggle alerts
- `E` — Export events
- `V` — Cycle view mode
- `F` — Filter by source
- `S` — Quick source filter
- `/` — Search text
- `H` — Help
- `Q` — Quit


## Advanced Features

- **Dated Folder Logging** — Organize logs by date and time
- **30-Day Auto-Cleanup** — Automatic log rotation and cleanup
- **Auto-Start** — Add to Windows startup
- **EXE Build** — Compile to standalone executable
- **Sound Alerts** — Audio alerts for warnings and errors
- **Event Export** — Export to JSON / CSV
- **Full-Screen Display** — No gaps, continuous scrolling
- **Slow Mode** — Comfortable reading speed
- **Event Deduplication** — 5-second window to reduce noise
- **Regex Search** — Advanced text filtering
- **Source Filtering** — Filter by monitor source
- **Bookmarks** — Mark important events
- **Highlights** — Highlight specific sources
- **Configurable Intervals** — Control how often each monitor polls
- **Per-Monitor Toggle** — Enable or disable any monitor
- **Structured Log Files** — One log file per monitor per session
- **JSON Configuration** — Simple, human-readable config file
- **Real-Time Rolling Display** — Always shows the newest events
- **Event Severity Filtering** — Focus on what matters
- **Process Tree Visualization** — Understand parent-child relationships
- **Network Connection Tracking** — See every new connection
- **Security Event Correlation** — Spot suspicious activity faster
- **Hardware Health Monitoring** — Temperature, battery, disk health
- **Windows Update Tracking** — Know when updates happen
- **Service State Monitoring** — Detect unexpected service changes
- **Registry Change Detection** — Catch unauthorized modifications
- **File System Monitoring** — Track file and directory changes
- **Scheduled Task Monitoring** — See what runs and when
- **PowerShell Execution Logging** — Audit script activity
- **Sysmon Integration** — Consume Sysmon events directly
- **Cloud Sync Monitoring** — Track OneDrive, Dropbox, Google Drive
- **Virtualization Support** — WSL, Docker, Hyper-V, Sandbox
- **Server Role Monitoring** — IIS, SQL, Exchange, AD
- **Certificate Monitoring** — Track certificate changes
- **Crypto Key Monitoring** — Detect key usage
- **Performance Counter Monitoring** — Deep system metrics
- **Memory Diagnostic Events** — Catch hardware memory issues
- **Boot Configuration Changes** — Detect boot tampering
- **Timezone Changes** — Track system time changes
- **Group Policy Changes** — Monitor policy updates
- **Proxy Setting Changes** — Detect network redirection
- **Hosts File Monitoring** — Catch DNS hijacking
- **USB Device Tracking** — See every device connect
- **Driver Load/Unload Events** — Spot suspicious drivers
- **Printer Queue Monitoring** — Track print jobs
- **Bluetooth Device Monitoring** — See nearby devices
- **Display Setting Changes** — Track resolution and layout
- **Audio Device Changes** — Monitor sound devices
- **Battery Health Tracking** — Know your battery status
- **Thermal Zone Monitoring** — Prevent overheating
- **Fan Speed Monitoring** — Detect cooling issues
- **GPU Monitoring** — Track GPU usage and status
- **SMART Disk Health** — Predict drive failures
- **Windows Hello / BitLocker** — Monitor security features
- **LAPS Password Changes** — Track local admin passwords
- **Credential Manager Events** — Detect credential access
- **Autorun Entry Monitoring** — Catch persistence attempts
- **AppLocker Events** — Monitor application control
- **AppCompat Events** — Track compatibility issues
- **SmartScreen Status** — Monitor reputation checks
- **UAC Setting Changes** — Detect privilege changes
- **Defender ATP Alerts** — Advanced threat protection
- **Defender Behavior Events** — Catch suspicious behavior
- **Defender Scan Results** — Track scan activity
- **Defender Exclusions** — Detect exclusion changes
- **Threat Detection** — Identify suspicious processes
- **Failed Login Tracking** — Detect brute force attempts
- **Event Log Channels** — Monitor all channels
- **Windows Error Reporting** — Catch application crashes
- **Windows Event Forwarding** — Centralized log collection
- **Active Directory Events** — Monitor domain activity
- **Exchange Service Monitoring** — Track mail server health
- **SQL Server Monitoring** — Track database services
- **IIS Website Monitoring** — Track web server status
- **Hyper-V VM Monitoring** — Track virtual machines
- **Docker Container Monitoring** — Track containers
- **WSL Distro Monitoring** — Track Linux subsystems
- **Windows Sandbox Events** — Monitor isolated environments
- **Recovery Status Monitoring** — Track system recovery
- **Store App Monitoring** — Track UWP apps
- **Windows Feature Changes** — Detect feature installs
- **Installed Software Tracking** — Know what is installed
- **Feature Update Tracking** — Monitor major updates
- **Update Telemetry** — Track update behavior
- **Windows Update Log** — Parse update logs
- **Windows Update Events** — Track update lifecycle
- **Log File Tailing** — Follow any log file
- **Amcache Monitoring** — Track execution artifacts
- **Prefetch Monitoring** — Detect program execution
- **Bag MRU Monitoring** — Track folder views
- **UserAssist Monitoring** — Track GUI program usage
- **Typed URL Monitoring** — Track browser URLs
- **Jump List Monitoring** — Track recent files
- **Recent Document Monitoring** — Track opened files
- **Application Log Monitoring** — Track app logs
- **Directory Change Monitoring** — Track folder changes
- **File Change Monitoring** — Track file changes
- **Website Availability Monitoring** — Track uptime
- **Port Monitoring** — Detect open ports
- **DNS Cache Monitoring** — Track DNS resolution
- **Network Profile Monitoring** — Track network changes
- **New Connection Monitoring** — Detect new connections
- **TCP Statistics** — Track TCP health
- **Network Adapter Monitoring** — Track adapter changes
- **Network Share Monitoring** — Track shared folders
- **WiFi Profile Monitoring** — Track wireless networks
- **LAN Device Discovery** — Find devices on your network
- **Performance Counter Monitoring** — Deep system metrics
- **SetupAPI Log Monitoring** — Track driver installs
- **Certificate Monitoring** — Track certificate changes
- **Crypto Key Monitoring** — Detect key usage
- **Windows Reset Monitoring** — Track system resets
- **Memory Diagnostic Events** — Catch hardware memory issues
- **Windows Performance Recorder** — Track performance traces
- **Windows Admin Center** — Monitor management events
- **Cloud Sync Monitoring** — Track OneDrive, Dropbox, Google Drive
- **Scheduled Task Monitoring** — See what runs and when
- **Task Execution Monitoring** — Track task runs
- **Sysmon Event Monitoring** — Consume Sysmon events
- **WinRM Event Monitoring** — Track remote management
- **PowerShell Execution Logging** — Audit script activity
- **Active Directory Events** — Monitor domain activity
- **Exchange Service Monitoring** — Track mail server health
- **SQL Server Monitoring** — Track database services
- **IIS Website Monitoring** — Track web server status
- **Hyper-V VM Monitoring** — Track virtual machines
- **Docker Container Monitoring** — Track containers
- **WSL Distro Monitoring** — Track Linux subsystems
- **Windows Sandbox Events** — Monitor isolated environments
- **Recovery Status Monitoring** — Track system recovery
- **Store App Monitoring** — Track UWP apps
- **Windows Feature Changes** — Detect feature installs
- **Installed Software Tracking** — Know what is installed
- **Feature Update Tracking** — Monitor major updates
- **Update Telemetry** — Track update behavior
- **Windows Update Log** — Parse update logs
- **Windows Update Events** — Track update lifecycle
- **Event Deduplication** — Reduce noise with a 5-second window
- **Severity Levels** — DEBUG, INFO, NOTICE, WARNING, ERROR, CRITICAL
- **Structured Data Fields** — Machine-readable event payloads
- **Location Information** — File paths, registry keys, network endpoints
- **Bookmark Support** — Mark and revisit important events
- **Highlight Support** — Visually emphasize specific sources
- **Regex Search** — Powerful text filtering
- **Source Filtering** — Focus on one or more monitors
- **Quick Source Filter** — Fast switching between sources
- **Pause / Resume** — Freeze the display when needed
- **Clear Events** — Reset the view instantly
- **Toggle Data Display** — Show or hide structured fields
- **Compact Mode** — One-line events for high-volume scenarios
- **Export Events** — JSON and CSV output
- **Full-Screen Mode** — No gaps, continuous scrolling
- **Slow Mode** — Comfortable reading speed
- **Sound Alerts** — Audio notifications for warnings and errors
- **Auto-Start** — Launch on Windows boot
- **EXE Build** — Standalone executable with PyInstaller
- **Config File** — JSON-based configuration
- **Per-Monitor Intervals** — Control polling frequency
- **Dated Folder Logging** — Logs organized by date and time
- **30-Day Auto-Cleanup** — Automatic log rotation
- **Structured Log Files** — One file per monitor per session
- **Real-Time Rolling Display** — Always shows the newest events
- **Multi-View Modes** — Normal, Dashboard, Alerts, Tree, Compact
- **Process Tree View** — Parent-child process relationships
- **Network Connection Tracking** — See every new connection
- **Security Event Correlation** — Spot suspicious activity faster
- **Hardware Health Monitoring** — Temperature, battery, disk health
- **Windows Update Tracking** — Know when updates happen
- **Service State Monitoring** — Detect unexpected service changes
- **Registry Change Detection** — Catch unauthorized modifications
- **File System Monitoring** — Track file and directory changes
- **Scheduled Task Monitoring** — See what runs and when
- **PowerShell Execution Logging** — Audit script activity
- **Sysmon Integration** — Consume Sysmon events directly
- **Cloud Sync Monitoring** — Track OneDrive, Dropbox, Google Drive
- **Virtualization Support** — WSL, Docker, Hyper-V, Sandbox
- **Server Role Monitoring** — IIS, SQL, Exchange, AD
- **Certificate Monitoring** — Track certificate changes
- **Crypto Key Monitoring** — Detect key usage
- **Performance Counter Monitoring** — Deep system metrics
- **Memory Diagnostic Events** — Catch hardware memory issues
- **Boot Configuration Changes** — Detect boot tampering
- **Timezone Changes** — Track system time changes
- **Group Policy Changes** — Monitor policy updates
- **Proxy Setting Changes** — Detect network redirection
- **Hosts File Monitoring** — Catch DNS hijacking
- **USB Device Tracking** — See every device connect
- **Driver Load/Unload Events** — Spot suspicious drivers
- **Printer Queue Monitoring** — Track print jobs
- **Bluetooth Device Monitoring** — See nearby devices
- **Display Setting Changes** — Track resolution and layout
- **Audio Device Changes** — Monitor sound devices
- **Battery Health Tracking** — Know your battery status
- **Thermal Zone Monitoring** — Prevent overheating
- **Fan Speed Monitoring** — Detect cooling issues
- **GPU Monitoring** — Track GPU usage and status
- **SMART Disk Health** — Predict drive failures
- **Windows Hello / BitLocker** — Monitor security features
- **LAPS Password Changes** — Track local admin passwords
- **Credential Manager Events** — Detect credential access
- **Autorun Entry Monitoring** — Catch persistence attempts
- **AppLocker Events** — Monitor application control
- **AppCompat Events** — Track compatibility issues
- **SmartScreen Status** — Monitor reputation checks
- **UAC Setting Changes** — Detect privilege changes
- **Defender ATP Alerts** — Advanced threat protection
- **Defender Behavior Events** — Catch suspicious behavior
- **Defender Scan Results** — Track scan activity
- **Defender Exclusions** — Detect exclusion changes
- **Threat Detection** — Identify suspicious processes
- **Failed Login Tracking** — Detect brute force attempts
- **Event Log Channels** — Monitor all channels
- **Windows Error Reporting** — Catch application crashes
- **Windows Event Forwarding** — Centralized log collection
- **Active Directory Events** — Monitor domain activity
- **Exchange Service Monitoring** — Track mail server health
- **SQL Server Monitoring** — Track database services
- **IIS Website Monitoring** — Track web server status
- **Hyper-V VM Monitoring** — Track virtual machines
- **Docker Container Monitoring** — Track containers
- **WSL Distro Monitoring** — Track Linux subsystems
- **Windows Sandbox Events** — Monitor isolated environments
- **Recovery Status Monitoring** — Track system recovery
- **Store App Monitoring** — Track UWP apps
- **Windows Feature Changes** — Detect feature installs
- **Installed Software Tracking** — Know what is installed
- **Feature Update Tracking** — Monitor major updates
- **Update Telemetry** — Track update behavior
- **Windows Update Log** — Parse update logs
- **Windows Update Events** — Track update lifecycle
