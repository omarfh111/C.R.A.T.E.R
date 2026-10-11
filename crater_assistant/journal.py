"""Model-free collector CLI; the optional worker calls only the guarded sidecar."""
import argparse
import json

from .experience import Journal
from .experience_analysis import ExperienceWorker, RemoteAssistant
from .server import live_capture_active, make_server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--media-root")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--allow-origin", action="append", default=[])
    parser.add_argument("--assistant-url", default="http://127.0.0.1:8766")
    parser.add_argument("--export", help="Write explicit operator-selected JSON snapshot, never RAG auto-import")
    parser.add_argument("--finish-interrupted-session", help="Explicit recovery after a producer crash; capture must be stopped")
    args = parser.parse_args(argv)
    journal = Journal(args.database, media_root=args.media_root)
    if args.export:
        from pathlib import Path
        destination = Path(args.export)
        with destination.open("x", encoding="utf-8") as output:
            json.dump(journal.snapshot(), output, ensure_ascii=False, indent=2)
        return
    if args.finish_interrupted_session:
        if live_capture_active():
            raise ValueError("M1 capture active or cannot be excluded")
        journal.finish(args.finish_interrupted_session, interrupted=True)
        return
    worker = ExperienceWorker(journal, RemoteAssistant(args.assistant_url))
    try:
        with make_server(None, args.port, allowed_origins=args.allow_origin, journal=journal, worker=worker) as server:
            print(f"Incident collector: http://127.0.0.1:{server.server_port}; no model required", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        worker.close()


if __name__ == "__main__":
    main()
