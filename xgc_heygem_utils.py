import subprocess
import os
import sys
import time
import socket
import torch
import numpy as np

def wait_for_port():
    timeout=60
    start_time = time.time()
    
    while True:
        try:
            with socket.create_connection(("127.0.0.1", "8383"), timeout=1):
                return True
        except (socket.error, OSError):
            if time.time() - start_time > timeout:
                return False
            time.sleep(1)

def is_xgc_heygem_running():
    try:
        result = subprocess.run(
            ["task-is-run", "heygem"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode == 0:
            return True
        else:
            return False
    except Exception as e:
        print(f"is_xgc_heygem_running error: {e}")
        return False
        
def start_heygem_service(volume_host_path):
    if is_xgc_heygem_running():
        return True

    try:
        result = subprocess.run(
            ["bash", "/root/heygem/start.sh"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode != 0:
            return False

        return wait_for_port()

    except Exception as e:
        print(f"start_heygem_service error: {e}")
        return False


def stop_heygem_service():
    try:
        result = subprocess.run(
            ["task-kill", "heygem"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode == 0:
            return True
        else:
            return False
    except Exception as e:
        print(f"stop_heygem_service error: {e}")
        return False