# Grafana Cloud Kubernetes Monitoring Integration

> Complete step-by-step guide for integrating Grafana Cloud Kubernetes Monitoring with your EKS cluster.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [What Gets Deployed](#2-what-gets-deployed)
3. [Get Grafana Cloud Credentials](#3-get-grafana-cloud-credentials)
4. [Create values.yaml](#4-create-valuesyaml)
5. [Deploy the Helm Chart](#5-deploy-the-helm-chart)
6. [Verify the Deployment](#6-verify-the-deployment)
7. [Access Grafana Cloud Dashboards](#7-access-grafana-cloud-dashboards)
8. [Querying Logs with Loki](#8-querying-logs-with-loki)
9. [kubectl Log Commands](#9-kubectl-log-commands)
10. [Cost](#10-cost)
11. [Troubleshooting](#11-troubleshooting)
12. [Rollback / Uninstall](#12-rollback--uninstall)

---

## 1. Prerequisites

| Tool | Purpose | Install Command (macOS) |
|------|---------|------------------------|
| `kubectl` | Talk to your EKS cluster | `brew install kubernetes-cli` |
| `helm` | Install the monitoring chart | `brew install helm` |
| Grafana Cloud account | Receive metrics and logs | [Sign up free](https://grafana.com) |

Verify connectivity to your cluster:

```bash
kubectl get nodes
```

---

## 2. What Gets Deployed

The [Grafana Kubernetes Monitoring Helm chart v4](https://github.com/grafana/k8s-monitoring-helm) installs:

| Component | Type | What it collects |
|-----------|------|-----------------|
| `alloy-metrics` | StatefulSet | Cluster metrics (kubelet, cAdvisor, kube-state-metrics) |
| `alloy-logs` | DaemonSet | Pod logs and node logs from every worker node |
| `alloy-singleton` | Deployment | Kubernetes cluster events |
| `kube-state-metrics` | Deployment | K8s object metadata as Prometheus metrics |
| `node-exporter` | DaemonSet | Host-level CPU, memory, disk, network metrics |
| `opencost` | Deployment | Cost attribution per namespace / pod |
| `kepler` | DaemonSet | Energy and power consumption metrics |

All data is sent to **Grafana Cloud** (managed Prometheus for metrics, managed Loki for logs).

---

## 3. Get Grafana Cloud Credentials

### 3.1 Activate Kubernetes Monitoring

1. Log in to [grafana.com](https://grafana.com) → **My Account**
2. Click your stack name
3. Click **Launch** next to **Kubernetes Monitoring**
4. Click **Activate** → confirm the dialog → click **Activate**
5. Click **Start sending data**

### 3.2 Configure the Cluster

In the **Cluster configuration** wizard:

| Step | Field | Value |
|------|-------|-------|
| 1 | Cluster name | `agentic-rag-cluster` |
| 1 | Namespace | `monitoring` |
| 1 | Platform | **Kubernetes (EKS on EC2, GKE, etc.)** |
| 2 | Monitoring type | **Kubernetes Monitoring** |
| 3 | Access Policy Token | Create new token with scopes: `metrics:write`, `logs:write` |
| 4 | Deployment method | **Helm** |

### 3.3 Copy the Generated Values

On Step 4 (Deployment), Grafana Cloud generates a Helm command. Copy the **four values** from it:

| Value | Example Format | Where it appears |
|-------|---------------|------------------|
| Prometheus remote_write URL | `https://prometheus-prod-XX.grafana.net/api/prom/push` | Under `destinations:` → `grafana-cloud-metrics:` |
| Metrics Instance ID | `1234567` | `auth.username` inside the metrics destination |
| Loki push URL | `https://logs-prod-XXX.grafana.net/loki/api/v1/push` | Under `destinations:` → `grafana-cloud-logs:` |
| Access Policy token | `glc_eyJ...` | `auth.password` inside both destinations |

> **Security:** Never commit the raw `values.yaml` with the token to git. It is already listed in `.gitignore`.

---

## 4. Create values.yaml

Create `deployment/grafana/values.yaml` in your repo. Use the credentials from Step 3:

```yaml
cluster:
  name: agentic-rag-cluster

destinations:
  grafana-cloud-metrics:
    type: prometheus
    url: https://prometheus-prod-43-prod-ap-south-1.grafana.net/api/prom/push
    auth:
      type: basic
      username: "YOUR_METRICS_INSTANCE_ID"
      password: YOUR_ACCESS_POLICY_TOKEN

  grafana-cloud-logs:
    type: loki
    url: https://logs-prod-028.grafana.net/loki/api/v1/push
    auth:
      type: basic
      username: "YOUR_LOGS_INSTANCE_ID"
      password: YOUR_ACCESS_POLICY_TOKEN

clusterMetrics:
  enabled: true
  collector: alloy-metrics

hostMetrics:
  enabled: true
  collector: alloy-metrics
  linuxHosts:
    enabled: true
  windowsHosts:
    enabled: false   # EKS nodes are Linux
  energyMetrics:
    enabled: true

costMetrics:
  enabled: true
  collector: alloy-metrics

clusterEvents:
  enabled: true
  collector: alloy-singleton

podLogsViaLoki:
  enabled: true
  collector: alloy-logs

collectors:
  alloy-metrics:
    presets:
      - clustered
      - statefulset
  alloy-singleton:
    presets:
      - singleton
  alloy-logs:
    presets:
      - filesystem-log-reader
      - daemonset

telemetryServices:
  kube-state-metrics:
    deploy: true
  node-exporter:
    deploy: true
  windows-exporter:
    deploy: false   # EKS nodes are Linux
  opencost:
    deploy: true
    metricsSource: grafana-cloud-metrics
    opencost:
      exporter:
        defaultClusterId: agentic-rag-cluster
      prometheus:
        existingSecretName: grafana-cloud-metrics-grafana-k8s-monitoring
        external:
          url: https://prometheus-prod-43-prod-ap-south-1.grafana.net/api/prom
  kepler:
    deploy: true
```

### Important Fixes Applied

| Issue | Fix |
|-------|-----|
| Trailing dots in URLs (`grafana.net./`) | Removed — should be `grafana.net/` |
| Windows metrics enabled | Disabled — EKS nodes are Linux |
| Fleet Management (`remoteConfig`) | Removed — not needed for basic setup |

---

## 5. Deploy the Helm Chart

```bash
# Add the Grafana Helm repository
helm repo add grafana https://grafana.github.io/helm-charts

# Update to get the latest chart versions
helm repo update

# Install the chart
helm upgrade --install \
  --atomic \
  --timeout 300s \
  grafana-k8s-monitoring \
  grafana/k8s-monitoring \
  --version "^4" \
  --namespace "monitoring" \
  --create-namespace \
  --values deployment/grafana/values.yaml
```

**What happens:**
- Creates the `monitoring` namespace
- Deploys Alloy Operator + 3 Alloy collectors
- Deploys kube-state-metrics, node-exporter, OpenCost, Kepler
- Begins scraping metrics and reading logs immediately

---

## 6. Verify the Deployment

### 6.1 Check Pods

```bash
kubectl get pods -n monitoring
```

Expected output — all pods should be `Running`:

```
NAME                                                         READY   STATUS    RESTARTS   AGE
grafana-k8s-monitoring-alloy-logs-xxxxx                    2/2     Running   0          2m
grafana-k8s-monitoring-alloy-metrics-0                     2/2     Running   0          2m
grafana-k8s-monitoring-alloy-singleton-xxxxx                 2/2     Running   0          2m
grafana-k8s-monitoring-kube-state-metrics-xxxxx            1/1     Running   0          2m
grafana-k8s-monitoring-node-exporter-xxxxx                 1/1     Running   0          2m
grafana-k8s-monitoring-opencost-xxxxx                      1/1     Running   0          2m
```

### 6.2 Verify Data is Flowing

Check the Alloy metrics collector logs for successful remote writes:

```bash
kubectl logs -n monitoring \
  statefulset/grafana-k8s-monitoring-alloy-metrics \
  --tail=20 | grep -E "remote_write|push|Done replaying"
```

You should see:
```
Done replaying WAL ... url=https://prometheus-prod-XX.grafana.net/api/prom/push
Remote storage resharding ... url=https://prometheus-prod-XX.grafana.net/api/prom/push
```

This confirms metrics are being pushed to Grafana Cloud.

---

## 7. Access Grafana Cloud Dashboards

### 7.1 Kubernetes Overview

1. Go to your Grafana stack URL
2. Navigate to **Observability → Kubernetes Overview**
3. Select cluster: `agentic-rag-cluster`
4. Select namespace: `production` or `monitoring`

**What you see:**
- Cluster health (CPU, memory, disk for each node)
- Pod list with status and resource usage
- Namespace breakdown
- Cost estimates (from OpenCost)
- Recent cluster events

### 7.2 Metrics Explorer

1. Go to **Explore**
2. Select **Prometheus** data source
3. Query examples:

```promql
# CPU usage by pod
rate(container_cpu_usage_seconds_total{namespace="production"}[5m])

# Memory usage by pod
container_memory_working_set_bytes{namespace="production"}

# Node CPU
100 - (avg(irate(node_cpu_seconds_total{mode="idle"}[5m])) by (instance) * 100)

# OpenSearch heap usage
opensearch_jvm_memory_used_bytes{area="heap"}
```

### 7.3 Cost Dashboard

OpenCost metrics are automatically available:

```promql
# Daily cost by namespace
sum(opencost_container_cpu_allocation) by (namespace)
```

---

## 8. Querying Logs with Loki

Since `alloy-logs` sends all pod logs to Grafana Cloud Loki, you can search historically (14+ days retention on Free tier).

### 8.1 Access Loki in Grafana

1. Go to **Explore**
2. Select **Loki** data source
3. Switch to **Code** mode for LogQL queries

### 8.2 Common LogQL Queries

| What you want | LogQL Query |
|--------------|-------------|
| All Airflow logs | `{namespace="production", app="airflow"}` |
| All API logs | `{namespace="production", app="rag-api"}` |
| All OpenSearch logs | `{namespace="production", pod=~"opensearch-.*"}` |
| All production logs | `{namespace="production"}` |
| All monitoring logs | `{namespace="monitoring"}` |
| Airflow ERROR lines | `{namespace="production", app="airflow"} \|= "ERROR"` |
| API request logs | `{namespace="production", app="rag-api"} \|= "GET /api"` |
| API 500 errors | `{namespace="production", app="rag-api"} \|= "500"` |
| OpenSearch health check | `{namespace="production", pod=~"opensearch-.*"} \|= "health"` |
| DAG import errors | `{namespace="production", app="airflow"} \|= "DagFileProcessor"` |

### 8.3 Loki Query Tips

**Filter by time:** Use the time picker in the top right (Last 1 hour, Last 6 hours, etc.)

**Show log volume:** Enable "Volume" to see log frequency spikes

**JSON parse (if apps log JSON):**
```
{namespace="production", app="rag-api"}
  | json
  | status_code = "500"
```

**Extract patterns:**
```
{namespace="production", app="rag-api"}
  |~ "POST /api/v1/ask .* (\d+)ms"
```

---

## 9. kubectl Log Commands

For immediate, real-time log access (useful when debugging live issues):

### 9.1 Airflow Logs

```bash
# Live tail all Airflow logs
kubectl logs -n production -l app=airflow -f

# Last 100 lines
kubectl logs -n production -l app=airflow --tail=100

# Specific Airflow pod
kubectl logs -n production airflow-xxxxx --tail=200

# Previous container (after crash / restart)
kubectl logs -n production -l app=airflow --previous --tail=100

# Find and read task logs inside the pod
kubectl exec -n production $(kubectl get pods -n production -l app=airflow -o jsonpath='{.items[0].metadata.name}') \
  -- find /opt/airflow/logs/dag_id=arxiv_paper_ingestion -name "*.log" -exec tail -50 {} +
```

### 9.2 API Application Logs

```bash
# Live tail all API pods
kubectl logs -n production -l app=rag-api -f

# Last 200 lines from specific pod
kubectl logs -n production rag-api-xxxxx --tail=200

# Previous container logs (after crash)
kubectl logs -n production -l app=rag-api --previous --tail=100

# All API pods with prefixes
kubectl logs -n production -l app=rag-api --all-containers --prefix --tail=50
```

### 9.3 OpenSearch Logs

```bash
kubectl logs -n production opensearch-0 --tail=50 -f
kubectl logs -n production -l app=opensearch-dashboards --tail=50
```

### 9.4 Monitoring / Grafana Alloy Logs

```bash
# Alloy metrics collector
kubectl logs -n monitoring statefulset/grafana-k8s-monitoring-alloy-metrics --tail=50 -f

# Alloy logs collector
kubectl logs -n monitoring daemonset/grafana-k8s-monitoring-alloy-logs --tail=50 -f

# Alloy singleton (events)
kubectl logs -n monitoring deployment/grafana-k8s-monitoring-alloy-singleton --tail=50 -f

# OpenCost
kubectl logs -n monitoring deployment/grafana-k8s-monitoring-opencost --tail=50 -f
```

### 9.5 All Namespace Logs

```bash
# All pods in production namespace
kubectl logs -n production --all-containers --prefix --tail=30

# All pods in monitoring namespace
kubectl logs -n monitoring --all-containers --prefix --tail=30
```

---

## 10. Cost

| Tier | Monthly Cost for 2-Node EKS Cluster |
|------|-----------------------------------|
| **Free** | **$0** |
| Pro | $19 base + usage (but Free tier allowance covers your cluster) |

**Free tier allowances:**
- 2,232 host-hours (~3 hosts running 24/7)
- 37,944 container-hours
- 10,000 active metric series
- 50 GB log ingestion

Your 2-node EKS cluster uses approximately:
- 1,440 host-hours/month (2 nodes × 24h × 30d)
- ~10,000 container-hours/month

**Well within the Free tier.** You only pay if you upgrade to Pro for longer retention (>14 days).

---

## 11. Troubleshooting

### No data in Grafana Cloud dashboards

```bash
# Check if Alloy metrics pod is running
kubectl get pods -n monitoring -l app.kubernetes.io/component=alloy-metrics

# Check for push errors
kubectl logs -n monitoring statefulset/grafana-k8s-monitoring-alloy-metrics --tail=50 | grep -i error

# Check endpoints are reachable from the pod
kubectl exec -n monitoring statefulset/grafana-k8s-monitoring-alloy-metrics -- \
  wget -qO- https://prometheus-prod-XX.grafana.net/api/prom/push
```

### Alloy logs pod crashing

```bash
# Check if node has enough disk for log reading
kubectl describe node $(kubectl get pods -n monitoring -l app.kubernetes.io/component=alloy-logs -o jsonpath='{.items[0].spec.nodeName}')

# Check Alloy logs for errors
kubectl logs -n monitoring daemonset/grafana-k8s-monitoring-alloy-logs --tail=50 | grep -i error
```

### Node Exporter not running

```bash
# Check daemonset status
kubectl get daemonset -n monitoring grafana-k8s-monitoring-node-exporter

# If EKS Fargate, Node Exporter is disabled by design — use kubelet metrics instead
```

---

## 12. Rollback / Uninstall

```bash
# Uninstall the Helm chart
helm uninstall grafana-k8s-monitoring -n monitoring

# Delete the namespace (removes all monitoring pods)
kubectl delete namespace monitoring

# Verify removal
kubectl get pods -n monitoring
```

To re-install, simply run the `helm upgrade --install` command from Step 5 again.

---

## Files in This Repo

| File | Purpose |
|------|---------|
| `deployment/grafana/values.yaml` | Grafana Cloud endpoints and credentials |
| `docs/grafana_integration.md` | This guide |

> **Warning:** `deployment/grafana/values.yaml` contains your Access Policy token. It is listed in `.gitignore`. Never commit it to git.
