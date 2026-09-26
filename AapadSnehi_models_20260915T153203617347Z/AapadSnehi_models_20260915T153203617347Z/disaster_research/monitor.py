"""Sample current research processes; measured peaks are lower bounds at 5 s cadence."""
import json
import time
import psutil
import subprocess
from .paths import REPORTS

def main():
    path=REPORTS/"sampled_memory_peaks.json"
    previous=json.loads(path.read_text()) if path.exists() else {}
    peaks=previous.get("rss_peak_bytes_by_command",{})
    gpu_peak=previous.get("gpu_total_used_mib_peak",0)
    while True:
        active=[]
        for process in psutil.process_iter(["pid","cmdline","memory_info"]):
            try:
                args=process.info["cmdline"] or []
                if any(arg.startswith("disaster_research") and arg!="disaster_research.monitor" for arg in args):
                    key=" ".join(args[1:]);rss=process.memory_info().rss
                    peaks[key]=max(peaks.get(key,0),rss);active.append(process.pid)
            except (psutil.NoSuchProcess,psutil.AccessDenied):
                pass
        try:
            gpu=subprocess.check_output(["nvidia-smi","--query-gpu=memory.used","--format=csv,noheader,nounits"],timeout=5,text=True)
            gpu_peak=max(gpu_peak,int(gpu.splitlines()[0]))
        except (OSError,ValueError,subprocess.SubprocessError):pass
        path.write_text(json.dumps({"cadence_seconds":5,"rss_peak_bytes_by_command":peaks,"gpu_total_used_mib_peak":gpu_peak,"gpu_note":"Device total including unrelated processes, not model-only allocation","system_available_bytes":psutil.virtual_memory().available,"active_pids":active,"updated_unix":time.time()},indent=2))
        if not active:break
        time.sleep(5)

if __name__ == "__main__":main()
