"""Optional five-finger tactile/bend viewer for stream_glove.py."""

import signal
import time
from concurrent.futures import Future

from tactile_glove import ADC_MAX, FINGER_NAMES


class GloveViewer:
    """Live raw readings in mirrored LH/RH panels, independent of acquisition."""

    def __init__(self, capture) -> None:
        import numpy as np
        from PySide6 import QtWidgets

        self.capture = capture
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        import pyqtgraph as pg

        self.window = pg.GraphicsLayoutWidget(
            title="Tactile Glove SDK — five-finger raw readings"
        )
        self.window.resize(1300, 620)
        self.headers = {}
        self.images = {}
        self.bars = {}
        self.fingers = {"lh": tuple(reversed(FINGER_NAMES)), "rh": tuple(FINGER_NAMES)}
        width = len(FINGER_NAMES) * 5 - 1
        centers = [5 * index + 2 for index in range(len(FINGER_NAMES))]
        for column, hand in enumerate(("lh", "rh"), start=1):
            self.window.ci.layout.setColumnStretchFactor(column, 1)
            selected = "waiting for data" if hand in capture.ports else "not selected"
            self.headers[hand] = self.window.addLabel(
                f"{hand.upper()} — {selected}", row=0, col=column
            )
            ticks = [
                (center, finger.title())
                for center, finger in zip(centers, self.fingers[hand])
            ]
            tactile = self.window.addPlot(
                row=1, col=column, title="Five 4×4 tactile patches — raw ADC"
            )
            tactile.getAxis("left").setWidth(60)
            tactile.getAxis("left").setStyle(showValues=False)
            tactile.getAxis("left").setPen(None)
            tactile.getAxis("bottom").setTicks([ticks])
            # Image coordinates increase downward; decoded row 0 is at the top.
            tactile.invertY(True)
            tactile.setXRange(-0.5, width + 0.5, padding=0)
            tactile.setYRange(0, 4, padding=0)
            tactile.setMouseEnabled(x=False, y=False)
            image = pg.ImageItem(
                np.full((4, width), np.nan), axisOrder="row-major", levels=(0, ADC_MAX)
            )
            tactile.addItem(image)
            self.images[hand] = image
            # Make individual pixels visible even when neighboring ADC values match.
            grid_x, grid_y = [], []
            for index in range(len(FINGER_NAMES)):
                left = 5 * index
                for edge in range(5):
                    grid_x.extend((left + edge, left + edge, left, left + 4))
                    grid_y.extend((0, 4, edge, edge))
            tactile.addItem(
                pg.PlotCurveItem(
                    grid_x, grid_y, connect="pairs", pen=pg.mkPen("#7c889c", width=1)
                )
            )
            scale = pg.ColorBarItem(
                values=(0, ADC_MAX),
                colorMap=pg.colormap.get("viridis"),
                interactive=False,
            )
            scale.setImageItem(image)
            scale.getAxis("right").enableAutoSIPrefix(False)
            scale.getAxis("right").setTicks(
                [[(value, str(value)) for value in (0, 1024, 2048, 3072, ADC_MAX)]]
            )
            self.window.addItem(scale, row=1, col=0 if hand == "lh" else 3)
            bend = self.window.addPlot(
                row=2, col=column, title="Bend — one channel per finger"
            )
            bend.getAxis("left").setWidth(60)
            bend.getAxis("left").enableAutoSIPrefix(False)
            bend.setLabel("left", "Raw ADC")
            bend.setYRange(0, ADC_MAX, padding=0)
            bend.setXRange(-0.5, width + 0.5, padding=0)
            bend.setMouseEnabled(x=False, y=False)
            bend.getAxis("bottom").setTicks([ticks])
            bars = pg.BarGraphItem(
                x=centers, height=[0] * len(FINGER_NAMES), width=1.6, brush="#00c800"
            )
            bend.addItem(bars)
            self.bars[hand] = bars
            image.setOpacity(0.3)
            bars.setOpacity(0.3)
        self.window.addLabel(
            f"Five fingers · 16 tactile pixels and one bend channel per finger · raw ADC 0–{ADC_MAX}",
            row=3,
            col=1,
            colspan=2,
        )
        for row, height, minimum in ((1, 260, 160), (2, 220, 150)):
            self.window.ci.layout.setRowPreferredHeight(row, height)
            self.window.ci.layout.setRowMinimumHeight(row, minimum)
            self.window.ci.layout.setRowStretchFactor(row, 1)

    def update(self) -> None:
        import numpy as np

        latest, counts, started = self.capture.snapshot()
        now = time.monotonic()
        now_ns = time.time_ns()
        for hand, frame in latest.items():
            age = max(0, now_ns - frame.host_timestamp_ns) / 1_000_000_000
            elapsed = max(now - started[hand], 1e-9)
            state = " · stale" if age >= 1 else ""
            self.headers[hand].setText(
                f"{hand.upper()} | {self.capture.ports[hand]} | {counts[hand]:,} packets<br>mean {counts[hand] / elapsed:.1f} Hz · frame age {age:.2f}s{state}"
            )
            image = np.full((4, len(FINGER_NAMES) * 5 - 1), np.nan)
            for index, finger in enumerate(self.fingers[hand]):
                image[:, 5 * index : 5 * index + 4] = np.asarray(
                    frame.tactile.finger_pressure[finger]
                ).reshape(4, 4)
            self.images[hand].setImage(image, autoLevels=False)
            self.bars[hand].setOpts(
                height=[
                    frame.tactile.finger_bend[finger] for finger in self.fingers[hand]
                ]
            )
            opacity = 1 if age < 1 else 0.3
            self.images[hand].setOpacity(opacity)
            self.bars[hand].setOpacity(opacity)

    def run(self, future: Future[None]) -> None:
        from pyqtgraph.Qt import QtCore

        error: Exception | None = None
        last_report = time.monotonic()

        def tick() -> None:
            nonlocal error, last_report
            try:
                # Closing the window can destroy its scene items while a
                # refresh is queued. Stop before touching those Qt objects.
                if future.done() or not self.window.isVisible():
                    self.capture.stop.set()
                    self.app.quit()
                    return
                self.update()
                if time.monotonic() - last_report >= 1:
                    print(self.capture.status(), flush=True)
                    last_report = time.monotonic()
            except Exception as exc:  # noqa: BLE001 -- Propagate rendering errors after cleanup.
                error = exc
                self.app.quit()

        timer = QtCore.QTimer(self.window)
        timer.timeout.connect(tick)
        previous_sigint = signal.signal(signal.SIGINT, lambda *_: self.app.quit())
        try:
            timer.start(40)
            self.window.show()
            self.app.exec()
        finally:
            timer.stop()
            self.capture.stop.set()
            self.window.close()
            signal.signal(signal.SIGINT, previous_sigint)
        if error is not None:
            raise error
