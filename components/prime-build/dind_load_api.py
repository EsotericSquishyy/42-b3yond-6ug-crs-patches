#!/usr/bin/env python3
"""
dind_load_api.py
A FastAPI service that provides Docker container CPU usage and system load information.

Requirements:
    - Python 3.7+
    - FastAPI and uvicorn
    - Docker daemon reachable at http://localhost:2375
      (or set DOCKER_HOST env var, e.g. http://10.0.0.5:2375)

Security warning: port 2375 is *unauthenticated* root access. Fire-wall or enable TLS ASAP.
"""

import json
import os
import time
import urllib.request
import urllib.error
import socket
from typing import Dict, Any, Optional, Tuple, List
from pathlib import Path
import datetime
import threading
import concurrent.futures

from fastapi import FastAPI
import uvicorn

app = FastAPI(title="Docker Load API", description="API for monitoring Docker container CPU usage and system load")

DOCKER_HOST = os.getenv("DOCKER_ENDPOINT", "http://localhost:2375").rstrip("/")
MAX_NUM_UPSCALE_INSTANCES = 10  # Max number of instances to scale up to
UPSCALE_COUNT = 0  # Track how many times we've requested upscaling
LAST_UPSCALE_TIME = None  # Track when we last requested upscaling
COOLDOWN_MINUTES = 5  # Cooldown period in minutes

# New state for incremental scaling
CURRENT_REQUESTED_INSTANCES = 2
MAX_INCREMENTAL_INSTANCES = 14

# Cache for container CPU usage
CACHED_CPU_USAGE = 0.0
CACHE_LOCK = threading.Lock()


def load_averages() -> Tuple[float, float, float]:
    """
    Read /proc/loadavg and return (1-min, 5-min, 15-min) load averages.
    """
    parts = Path("/proc/loadavg").read_text().split()
    return tuple(float(x) for x in parts[:3])  # type: ignore


def to_percent(loads: Tuple[float, float, float], cpus: int) -> List[float]:
    """
    Convert raw load averages to % of total CPU capacity.
    Example: load 4.0 on an 8-core host ⇒ 50 %.
    """
    return [l / cpus * 100.0 for l in loads]


def _get(url: str, docker_host: Optional[str] = None) -> Any:
    host = docker_host or DOCKER_HOST
    try:
        with urllib.request.urlopen(f"{host}{url}") as resp:
            try:
                return json.load(resp)
            except json.JSONDecodeError:
                # Handle empty or invalid JSON responses
                return None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None  # Container not found
        raise  # Re-raise other HTTP errors
    except urllib.error.URLError:
        return None  # Docker daemon not available


def _stats_once(cid: str, docker_host: Optional[str] = None) -> Optional[Dict[str, Any]]:
    result = _get(f"/containers/{cid}/stats?stream=false", docker_host)
    return result  # Will be None if container was not found


def _cpu_percent(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    """Compute CPU% between two stats snapshots of the *same* container."""
    cpu_delta = b["cpu_stats"]["cpu_usage"]["total_usage"] \
                - a["cpu_stats"]["cpu_usage"]["total_usage"]
    sys_delta = b["cpu_stats"]["system_cpu_usage"] \
                - a["cpu_stats"]["system_cpu_usage"]
    if sys_delta <= 0 or cpu_delta < 0:
        return 0.0  # no data yet
    online = b["cpu_stats"].get("online_cpus") or len(
        b["cpu_stats"]["cpu_usage"].get("percpu_usage", [])) or 1
    return (cpu_delta / sys_delta) * online * 100.0


def get_container_cpu_usage() -> float:
    """Calculate the total CPU usage of all running containers with a 150-second timeout."""
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(_get_container_cpu_usage_impl)
        try:
            return future.result(timeout=150)
        except concurrent.futures.TimeoutError:
            return 3200.0

def _get_container_cpu_usage_impl() -> float:
    """Implementation of container CPU usage calculation."""
    # Check if we should use the headless service for multiple Docker hosts
    headless_svc_name = os.getenv("HEADLESS_SVC_NAME")
    
    if headless_svc_name:
        hostname = os.getenv("HOSTNAME", "localhost")
        namespace = os.getenv("NAMESPACE", "default")
        endpoint_host = f"{hostname}.{headless_svc_name}.{namespace}.svc.cluster.local"
        
        try:
            # Resolve the hostname to get all IP addresses
            ip_addresses = socket.gethostbyname_ex(endpoint_host)[2]
            max_cpu_usage = 0.0
            
            # Iterate over each IP and find the one with highest CPU usage
            for ip in ip_addresses:
                docker_host = f"http://{ip}:2375"
                cpu_usage = _get_single_host_cpu_usage(docker_host)
                max_cpu_usage = max(max_cpu_usage, cpu_usage)
            
            return max_cpu_usage
        except (socket.gaierror, socket.error):
            # Fall back to standard behavior if DNS resolution fails
            return _get_single_host_cpu_usage()
    else:
        # Standard behavior, use DOCKER_HOST
        return _get_single_host_cpu_usage()


def _get_single_host_cpu_usage(docker_host: Optional[str] = None) -> float:
    # 1. list running containers
    containers = [c["Id"] for c in _get("/containers/json", docker_host) or []]
    if not containers:
        return 0.0

    # 2. first snapshot
    snap1 = {}
    for cid in containers:
        stats = _stats_once(cid, docker_host)
        if stats is not None:
            snap1[cid] = stats

    # 3. wait a short interval and take second snapshot
    time.sleep(0.5)
    snap2 = {}
    for cid in containers:
        stats = _stats_once(cid, docker_host)
        if stats is not None:
            snap2[cid] = stats

    # 4. compute per-container CPU% and sum them
    total_cpu = 0.0
    for cid in snap1:
        if cid in snap2:  # Only process if container exists in both snapshots
            try:
                total_cpu += _cpu_percent(snap1[cid], snap2[cid])
            except KeyError:
                # stats incomplete for this container; ignore
                pass

    return total_cpu


def update_cpu_usage_cache():
    """Background task to update the CPU usage cache every 300 seconds."""
    global CACHED_CPU_USAGE
    
    # Update the cache
    local_stats = get_container_cpu_usage()

    with CACHE_LOCK:
        CACHED_CPU_USAGE = local_stats
    
    # Schedule the next update
    threading.Timer(240, update_cpu_usage_cache).start()


@app.get("/load")
async def get_load():
    """
    Get the CPU usage of all containers and system load averages.
    """
    global UPSCALE_COUNT, LAST_UPSCALE_TIME, CURRENT_REQUESTED_INSTANCES
    
    # Use cached CPU usage
    with CACHE_LOCK:
        total_cpu = CACHED_CPU_USAGE
    
    logical_cpus = os.cpu_count() or 1
    l1, l5, l15 = load_averages()
    
    # Determine if we are in a cooldown period from a previous upscale action
    in_cooldown = False
    if LAST_UPSCALE_TIME is not None:
        time_since_last_upscale = (datetime.datetime.now() - LAST_UPSCALE_TIME).total_seconds() / 60
        if time_since_last_upscale < COOLDOWN_MINUTES:
            in_cooldown = True
    
    # Logic for adjusting CURRENT_REQUESTED_INSTANCES based on CPU load
    if total_cpu / logical_cpus > 70.0:
        # High load: try to scale up if not in cooldown and not at max instances
        if CURRENT_REQUESTED_INSTANCES < MAX_INCREMENTAL_INSTANCES:
            CURRENT_REQUESTED_INSTANCES += 1
            UPSCALE_COUNT += 1
            LAST_UPSCALE_TIME = datetime.datetime.now()
        # If in cooldown or already at max, CURRENT_REQUESTED_INSTANCES remains unchanged.
    
    num_instances_to_return = CURRENT_REQUESTED_INSTANCES

    return {
        "num_requested": num_instances_to_return,
        "logical_cpus": logical_cpus,
        "load_container": total_cpu,
        "cooldown": in_cooldown, # Report cooldown status that affected this cycle's decision
        "load_sys": [l1, l5, l15]
    }


@app.get("/status")
async def get_status():
    """
    Check if Docker daemon is reachable.
    """
    try:
        with urllib.request.urlopen(f"{DOCKER_HOST}/_ping") as resp:
            if resp.status == 200:
                return {"status": "UP"}
    except (urllib.error.URLError, urllib.error.HTTPError):
        pass
    
    return {"status": "DOWN"}


if __name__ == "__main__":
    # Start the background task to update the CPU usage cache
    update_cpu_usage_cache()
    uvicorn.run(app, host="0.0.0.0", port=8000)
