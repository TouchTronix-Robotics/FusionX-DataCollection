"""Stream one or two assigned glove ports, optionally showing tactile/bend data."""

import argparse
import math
import time
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from threading import Event, Lock

from tactile_glove import GloveFrame, GloveReader


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "port", nargs="?", help="One serial port, e.g. COM3 or /dev/ttyUSB0"
    )
    parser.add_argument(
        "--hand", choices=("lh", "rh"), help="Single-port hand; default: lh"
    )
    parser.add_argument(
        "--left", metavar="PORT", help="Assign this serial port to the left glove"
    )
    parser.add_argument(
        "--right", metavar="PORT", help="Assign this serial port to the right glove"
    )
    parser.add_argument("--baudrate", type=int, default=1_000_000)
    parser.add_argument("--seconds", type=float, help="Stop after this many seconds")
    parser.add_argument(
        "--viewer", action="store_true", help="Show live tactile heatmaps and bend bars"
    )
    args = parser.parse_args(argv)
    named_ports = {
        hand: port for hand, port in (("lh", args.left), ("rh", args.right)) if port
    }
    if args.port is not None:
        if named_ports:
            parser.error(
                "use a single port with --hand, or assign ports with --left/--right"
            )
        args.hand = args.hand or "lh"
        args.ports = {args.hand: args.port}
    else:
        if not named_ports:
            parser.error("provide a serial port or assign ports with --left/--right")
        if args.hand is not None:
            parser.error("--hand applies only to a single positional port")
        args.ports = named_ports
    if len(set(args.ports.values())) != len(args.ports):
        parser.error("each hand must use a distinct serial port")
    if args.baudrate <= 0:
        parser.error("--baudrate must be positive")
    if args.seconds is not None and (
        not math.isfinite(args.seconds) or args.seconds <= 0
    ):
        parser.error("--seconds must be a finite positive duration")
    return args


class Capture:
    """One acquisition worker per port; rendering consumes only the latest frame."""

    def __init__(
        self, ports: dict[str, str], baudrate: int, seconds: float | None
    ) -> None:
        self.ports = ports
        self.baudrate = baudrate
        self.seconds = seconds
        self.stop = Event()
        self.lock = Lock()
        self.started: dict[str, float] = {}
        self.counts: Counter[str] = Counter()
        self.latest: dict[str, GloveFrame] = {}

    def _read_hand(self, hand: str, port: str) -> None:
        if self.stop.is_set():
            return
        with GloveReader(port, hand=hand, baudrate=self.baudrate) as glove:
            started = time.monotonic()
            with self.lock:
                self.started[hand] = started
            while not self.stop.is_set():
                if (
                    self.seconds is not None
                    and time.monotonic() - started >= self.seconds
                ):
                    break
                frame = glove.read_frame()
                if frame is not None:
                    with self.lock:
                        self.counts[hand] += 1
                        self.latest[hand] = frame

    def run(self) -> None:
        with ThreadPoolExecutor(
            max_workers=len(self.ports), thread_name_prefix="glove-port"
        ) as executor:
            futures = [
                executor.submit(self._read_hand, hand, port)
                for hand, port in self.ports.items()
            ]
            try:
                for future in as_completed(futures):
                    future.result()
            finally:
                self.stop.set()

    def snapshot(self) -> tuple[dict[str, GloveFrame], Counter[str], dict[str, float]]:
        with self.lock:
            return self.latest.copy(), self.counts.copy(), self.started.copy()

    def status(self) -> str:
        latest, counts, started = self.snapshot()
        now = time.monotonic()
        now_ns = time.time_ns()
        parts = []
        for hand in self.ports:
            frame = latest.get(hand)
            if frame is None:
                state = "waiting for data" if hand in started else "connecting"
                parts.append(f"{hand.upper()}: {state}")
            else:
                elapsed = max(now - started[hand], 1e-9)
                age = max(0, now_ns - frame.host_timestamp_ns) / 1_000_000_000
                parts.append(
                    f"{hand.upper()}: {counts[hand]} packets, mean {counts[hand] / elapsed:.1f} Hz, last frame {age:.2f}s ago"
                )
        return "; ".join(parts)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    capture = Capture(args.ports, args.baudrate, args.seconds)
    viewer = None
    if args.viewer:
        from glove_viewer import GloveViewer

        viewer = GloveViewer(capture)
    print("Streaming glove data. Press Ctrl+C or close the viewer to stop.", flush=True)
    with ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="glove-capture"
    ) as executor:
        future = executor.submit(capture.run)
        try:
            if viewer is not None:
                viewer.run(future)
            else:
                while not future.done():
                    if not wait([future], timeout=1).done:
                        print(capture.status(), flush=True)
        except KeyboardInterrupt:
            pass
        finally:
            capture.stop.set()
            future.result()
    summary = ", ".join(
        f"{hand.upper()}={count}" for hand, count in sorted(capture.counts.items())
    )
    print(f"Captured {sum(capture.counts.values())} packets ({summary or 'no data'}).")


if __name__ == "__main__":
    main()
