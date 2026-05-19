"""Run the grey lit harvester and capture output to a log file."""
import sys
import traceback

# Redirect output to log file
log_path = "_grey_lit_harvest.log"
class Tee:
    def __init__(self, *files):
        self.files = files
    def write(self, data):
        for f in self.files:
            f.write(data)
            f.flush()
    def flush(self):
        for f in self.files:
            f.flush()

log_file = open(log_path, "w", encoding="utf-8")
sys.stdout = Tee(sys.__stdout__, log_file)
sys.stderr = Tee(sys.__stderr__, log_file)

try:
    from grey_lit_harvester import harvest_grey_lit
    sources = sys.argv[1:] if len(sys.argv) > 1 else None
    harvest_grey_lit(sources)
except Exception as e:
    traceback.print_exc()
finally:
    log_file.close()
