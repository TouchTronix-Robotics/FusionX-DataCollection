"""Stream one or two glove ports, optionally displaying a live raw-data viewer."""

import argparse
import math
import time
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, wait
from threading import Event, Lock

from touchtronix_glove import GloveFrame, GloveReader


class Capture:
    """Read serial data on one worker, independently of the GUI thread."""

    def __init__(self, ports: list[str], baudrate: int, seconds: float | None, *, preview: bool = False) -> None:
        self.ports = ports
        self.baudrate = baudrate
        self.seconds = seconds
        self.stop = Event()
        self.lock = Lock()
        self.started: float | None = None
        self.counts: Counter[str] = Counter()
        self.latest: dict[str, GloveFrame] = {}
        # About five seconds at 1.1 kHz/hand. This bounded buffer is for display only.
        self.history: dict[str, deque[tuple[float, ...]]] = (
            {hand: deque(maxlen=6000) for hand in ("lh", "rh")} if preview else {}
        )

    def run(self) -> None:
        with GloveReader(self.ports, baudrate=self.baudrate) as gloves:
            self.started = time.monotonic()
            while not self.stop.is_set():
                if self.seconds is not None and time.monotonic() - self.started >= self.seconds:
                    break
                frame = gloves.read_frame()
                if frame is None:
                    continue
                with self.lock:
                    self.counts[frame.hand] += 1
                    self.latest[frame.hand] = frame
                    if self.history and frame.imu is not None:
                        imu = frame.imu
                        self.history[frame.hand].append(
                            (
                                frame.timestamp,
                                *imu.quaternion,
                                *(imu.gyro or (math.nan,) * 3),
                                *(imu.accel or (math.nan,) * 3),
                                *(imu.magnetometer or (math.nan,) * 3),
                            )
                        )

    def status(self) -> str:
        with self.lock:
            counts = self.counts.copy()
            latest = self.latest.copy()
        if self.started is None:
            return "Connecting to glove ports..."
        elapsed = max(time.monotonic() - self.started, 1e-9)
        now_ns = time.time_ns()
        return (
            "; ".join(
                f"{hand.upper()}: {count} packets, mean {count / elapsed:.1f} Hz, "
                f"last frame {max(0, now_ns - latest[hand].host_timestamp_ns) / 1e9:.1f}s ago"
                for hand, count in sorted(counts.items())
            )
            or "Waiting for glove data..."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ports", nargs="+", help="One or two serial ports, e.g. /dev/ttyUSB0 /dev/ttyUSB1")
    parser.add_argument("--baudrate", type=int, default=6_000_000)
    parser.add_argument("--seconds", type=float, help="Stop after this many seconds; default: until Ctrl+C")
    parser.add_argument("--viewer", action="store_true", help="Show live plots")
    args = parser.parse_args()
    if len(args.ports) > 2 or len(set(args.ports)) != len(args.ports):
        parser.error("provide one or two distinct serial ports")

    capture = Capture(args.ports, args.baudrate, args.seconds, preview=args.viewer)
    viewer = None
    if args.viewer:
        from glove_viewer import GloveViewer

        viewer = GloveViewer(capture)
    print("Streaming glove data. Press Ctrl+C or close the viewer to stop.", flush=True)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="glove-capture") as executor:
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
            future.result()  # Propagate acquisition errors only after resources have closed.
    summary = ", ".join(f"{hand.upper()}={count}" for hand, count in sorted(capture.counts.items()))
    print(f"Captured {sum(capture.counts.values())} packets ({summary or 'no data'}).")


if __name__ == "__main__":
    main()
