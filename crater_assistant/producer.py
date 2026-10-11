"""Optional native producer lifecycle and warnings, entirely outside telemetry v1."""
import json
from pathlib import Path
import queue
import threading
import uuid

from .experience import Journal, now


class ProducerJournal:
    def __init__(self, args):
        self.journal = Journal(args.incident_journal)
        rover = "rover-1"  # Existing scenario and live M1 pipeline default, not an inferred identity.
        provenance = "live_inference" if args.perception_video else "synthetic"
        if args.input:
            with args.input.open(encoding="utf-8") as source:
                first = json.loads(source.readline(1048577))
            rover, provenance = first["roverId"], "historical_replay"
        self.session = self.journal.begin(rover, provenance)
        self.queue = queue.Queue(maxsize=16)
        self.dropped = self.failed = self.recorded = 0
        self.thread = threading.Thread(target=self.run, daemon=True, name="crater-incident-writer")
        self.thread.start()
        print(f"Incident session: {self.session['sessionId']} ({provenance}; radio simulated)", flush=True)

    def warning(self, summary, frame=None):
        payload = dict(eventId=str(uuid.uuid4()), sessionId=self.session["sessionId"], kind="producer_warning",
                       eventAt=now(), summary=str(summary)[:1000], triggerKey="producer_warning", frame=frame)
        try:
            self.queue.put_nowait(payload)
        except queue.Full:
            self.dropped += 1

    def run(self):
        while True:
            item = self.queue.get()
            try:
                if item is None:
                    return
                try:
                    self.journal.record(item, producer=True)
                    self.recorded += 1
                except (ValueError, OSError, KeyError):
                    self.failed += 1
                except Exception:
                    self.failed += 1
            finally:
                self.queue.task_done()

    def close(self, interrupted):
        # Only a tiny bounded event queue is drained, never a model request.
        self.queue.put(None, timeout=1)
        self.thread.join(timeout=4)
        if self.thread.is_alive():
            raise ValueError("Incident writer did not finish; capture session remains blocked")
        self.journal.finish(self.session["sessionId"], interrupted=interrupted)
        return dict(sessionId=self.session["sessionId"], recorded=self.recorded, dropped=self.dropped,
                    failed=self.failed, analysis="deferred; not a telemetry or driving action")
