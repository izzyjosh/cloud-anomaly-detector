# Cloud Anomaly Detector

Real-time anomaly detection pipeline for web traffic with automated IP blocking, Slack alerts, and a live metrics dashboard.

## Live Grading Endpoints

Update this section before submission so graders can test directly.

- Server IP: 16.16.100.88
- Dashboard URL: https://anomaly-dashboard.duckdns.org
- Metrics API URL: https://anomaly-dashboard.duckdns.org/metrics
- GitHub Repo (public): https://github.com/izzyjosh/cloud-anomaly-detector

## Language Choice And Why

This project uses Python.

Why Python was selected:

- Fast implementation of streaming log processing and detection logic.
- Strong standard library support for queues, statistics, threading, and file I/O.
- Clear and maintainable code for baseline math and anomaly decision rules.
- Easy integration with FastAPI for dashboard APIs and with Slack webhooks.

## System Architecture

The stack has three main services:

- nginx: Public edge reverse proxy (ports 80/443). Writes JSON access logs.
- nextcloud: Upstream app service behind nginx.
- detector: Monitors logs, computes anomalies, queues bans/unbans, serves dashboard API.

Traffic flow:

1. Client request reaches nginx.
2. nginx writes JSON log lines to /var/log/nginx/hng-access.log.
3. detector tails that log file in real time.
4. detector updates per-second counters and compares rates against baseline.
5. On anomaly, detector queues ban requests to /app/shared/ban_queue.txt.
6. Host ban worker reads queue files and applies actual firewall rules on the host.

## Sliding Window Logic (deque + eviction)

The detector uses fixed-size deques as rolling windows.

- Global window: deque(maxlen=60)
- Per-IP window: defaultdict of deque(maxlen=60)

How it works:

1. Incoming requests increment per-second counters (global and per-IP).
2. A ticker thread flushes counters once per second into the deques.
3. Because maxlen=60, each deque always keeps only the latest 60 seconds.
4. Old entries are evicted automatically by deque when new ones are appended.

Rate interpretation:

- Sum of counts over 60 seconds divided by WINDOW_SIZE gives requests/second.
- This keeps baseline and runtime rates in matching units.

## Baseline Logic

Baseline implementation details:

- Global baseline window size: 1800 seconds (30 minutes)
- Hourly baseline window size: 1800 per-second samples per hour bucket
- Recalculation interval: every 60 seconds
- Startup warm-up: anomaly actions blocked until minimum baseline samples are available

Computed baseline fields:

- mean: average request count per second
- stddev: standard deviation of per-second counts
- error_rate: error fraction from tracked status codes

Floor and safety values used:

- stddev floor = 1 when computed stddev is 0 (prevents divide-by-zero)
- default error_rate fallback = 0.01 when denominator is empty
- global baseline compute requires at least 10 samples
- hourly baseline is trusted only after at least 900 samples (15 minutes)

Detection uses:

- Z-score threshold
- Spike multiplier threshold
- Error surge multiplier for adaptive sensitivity

## Ban/Unban Design

This implementation uses queue files for host enforcement.

- detector writes ban requests to /app/shared/ban_queue.txt
- detector writes unban requests to /app/shared/unban_queue.txt
- host worker is responsible for applying/removing firewall rules

This avoids network namespace issues where container-only iptables rules do not block edge traffic globally.

## Fresh VPS Setup Guide

The following steps provision a fresh Ubuntu VPS and bring the full stack online.

### 1. Prepare DNS And Firewall

1. Point anomaly-dashboard.duckdns.org to your VPS public IP.
2. Open ports 80 and 443 in cloud firewall/security group.

### 2. Install Required Packages

```bash
sudo apt update
sudo apt install -y git docker.io docker-compose-plugin nginx certbot python3-certbot-nginx
sudo systemctl enable --now docker
```

### 3. Clone Project

```bash
git clone https://github.com/YOUR_USERNAME/cloud-anomaly-detector.git
cd cloud-anomaly-detector
```

### 4. Configure Environment

Create .env in repo root:

```bash
cat > .env << 'EOF'
WEB_HOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
EOF
```

### 5. Configure TLS Certificates

```bash
sudo certbot certonly --standalone -d anomaly-dashboard.duckdns.org
```

Certificates are expected at:

- /etc/letsencrypt/live/anomaly-dashboard.duckdns.org/fullchain.pem
- /etc/letsencrypt/live/anomaly-dashboard.duckdns.org/privkey.pem

### 6. Start Stack

```bash
docker compose up -d --build
```

### 7. Install Host Ban Worker (required)

Create a simple host worker that reads queue files and applies iptables rules:

```bash
sudo mkdir -p /var/lib/anomaly
sudo touch /var/lib/anomaly/ban_queue.txt /var/lib/anomaly/unban_queue.txt
```

Create /usr/local/bin/anomaly-ban-worker.sh:

```bash
sudo tee /usr/local/bin/anomaly-ban-worker.sh > /dev/null << 'EOF'
#!/usr/bin/env bash
set -euo pipefail

BAN_FILE="/var/lib/anomaly/ban_queue.txt"
UNBAN_FILE="/var/lib/anomaly/unban_queue.txt"

touch "$BAN_FILE" "$UNBAN_FILE"

while true; do
	if [[ -s "$BAN_FILE" ]]; then
		while IFS=, read -r ip duration; do
			[[ -z "${ip:-}" ]] && continue
			iptables -C DOCKER-USER -s "$ip" -j DROP 2>/dev/null || iptables -I DOCKER-USER 1 -s "$ip" -j DROP
		done < "$BAN_FILE"
		: > "$BAN_FILE"
	fi

	if [[ -s "$UNBAN_FILE" ]]; then
		while IFS= read -r ip; do
			[[ -z "${ip:-}" ]] && continue
			iptables -D DOCKER-USER -s "$ip" -j DROP 2>/dev/null || true
		done < "$UNBAN_FILE"
		: > "$UNBAN_FILE"
	fi

	sleep 2
done
EOF
```

```bash
sudo chmod +x /usr/local/bin/anomaly-ban-worker.sh
```

Create systemd service /etc/systemd/system/anomaly-ban-worker.service:

```bash
sudo tee /etc/systemd/system/anomaly-ban-worker.service > /dev/null << 'EOF'
[Unit]
Description=Anomaly Ban Queue Worker
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/anomaly-ban-worker.sh
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now anomaly-ban-worker.service
```

### 8. Verify Everything

```bash
docker compose ps
docker compose logs -f detector
sudo iptables -L DOCKER-USER -n --line-numbers
curl -I https://anomaly-dashboard.duckdns.org
curl https://anomaly-dashboard.duckdns.org/metrics
```

## Configuration Summary

Main config file: detector/config.yaml

Important values:

- thresholds.z_score_max
- thresholds.spike_multiplier
- thresholds.error_multiplier
- thresholds.window_size
- thresholds.warmup_seconds (optional)
- blocker.ban_duration

## Operational Notes

- Repeated alerts for the same already-banned IP are suppressed by code.
- During warm-up, state updates continue but anomaly actions are deferred.
- If you change domain or certificate paths, update nginx/nginx.conf accordingly.