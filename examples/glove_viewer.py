"""Optional tactile-first live viewer used by stream_glove.py."""

import signal
import time
from concurrent.futures import Future


class GloveViewer:
    """SDK inspection window; acquisition remains in the capture worker."""

    def __init__(self, capture) -> None:
        import numpy as np
        import pyqtgraph as pg

        self.capture = capture
        self.app = pg.mkQApp("TouchTronix FusionX Glove SDK")
        self.window = pg.GraphicsLayoutWidget(title="TouchTronix FusionX — raw glove stream")
        self.window.resize(1300, 950)
        self.headers = {}
        self.images = {}
        self.palms = {}
        self.bars = {}
        self.curves = {}
        self.fingers = ("thumb", "index", "middle", "ring", "little")
        colors = ("#56b4e9", "#e69f00", "#009e73", "#cc79a7")
        finger_ticks = [(4 * index + 1.5, finger.title()) for index, finger in enumerate(self.fingers)]
        axis_width = 55  # Match plot margins so pad bars stay beneath their fingertip patches.
        for column, hand in enumerate(("lh", "rh"), start=1):
            self.window.ci.layout.setColumnStretchFactor(column, 1)
            self.headers[hand] = self.window.addLabel(f"{hand.upper()} — waiting for data", row=0, col=column)
            tactile = self.window.addPlot(row=1, col=column, title="Fingertips — raw ADC, 0–255")
            tactile.getAxis("left").setWidth(axis_width)
            tactile.getAxis("left").setStyle(showValues=False)
            tactile.getAxis("left").setPen(None)
            tactile.getAxis("bottom").setTicks([finger_ticks])
            tactile.invertY(True)
            tactile.setXRange(-1, 20, padding=0)
            tactile.setYRange(0, 4, padding=0)
            tactile.setMouseEnabled(x=False, y=False)
            image = pg.ImageItem(np.full((4, 19), np.nan), axisOrder="row-major", levels=(0, 255))
            tactile.addItem(image)
            self.images[hand] = image
            palm = self.window.addPlot(row=2, col=column, title="Palm — 72 sensors; zero-based row/column indices")
            palm.getAxis("left").setWidth(axis_width)
            palm.getAxis("left").setTicks([[(index + 0.5, str(index)) for index in range(5)]])
            palm.getAxis("bottom").setTicks([[(index + 0.5, str(index)) for index in range(15)]])
            palm.invertY(True)
            palm.setXRange(-0.5, 15.5, padding=0)
            palm.setYRange(0, 5, padding=0)
            palm.setMouseEnabled(x=False, y=False)
            palm_image = pg.ImageItem(np.full((5, 15), np.nan), axisOrder="row-major", levels=(0, 255))
            palm.addItem(palm_image)
            self.palms[hand] = palm_image
            scale = pg.ColorBarItem(values=(0, 255), colorMap=pg.colormap.get("viridis"), interactive=False)
            scale.setImageItem([image, palm_image])
            scale.getAxis("right").setTicks([[(value, str(value)) for value in (0, 64, 128, 192, 255)]])
            self.window.addItem(scale, row=1, col=0 if hand == "lh" else 3, rowspan=2)
            pads = self.window.addPlot(row=3, col=column, title="Bend channels — [0] blue; [1] orange")
            pads.getAxis("left").setWidth(axis_width)
            pads.setLabel("left", "Raw ADC")
            pads.setYRange(0, 255, padding=0)
            pads.setXRange(-1, 20, padding=0)
            pads.setMouseEnabled(x=False, y=False)
            pads.getAxis("bottom").setTicks([finger_ticks])
            self.bars[hand] = pg.BarGraphItem(
                x=[4 * index + 1.5 + offset for index in range(5) for offset in (-0.45, 0.45)],
                height=[0] * 10,
                width=0.8,
                brushes=[color for _ in range(5) for color in colors[:2]],
            )
            pads.addItem(self.bars[hand])
            self.curves[hand] = []
            imu_layout = self.window.addLayout(row=4, col=column)
            for index, (title, channels) in enumerate(
                (("Quaternion", "wxyz"), ("Gyro (rad/s)", "xyz"), ("Accel (m/s²)", "xyz"), ("Magnetometer", "xyz"))
            ):
                plot = imu_layout.addPlot(row=index // 2, col=index % 2, title=title)
                plot.getAxis("left").setWidth(42)
                plot.getAxis("left").enableAutoSIPrefix(False)
                plot.setXRange(-5, 0, padding=0)
                plot.setMouseEnabled(x=False, y=True)
                plot.showGrid(x=True, y=True, alpha=0.2)
                legend = plot.addLegend(offset=(3, 3), colCount=2, labelTextSize="8pt")
                legend.layout.setContentsMargins(0, 0, 0, 0)
                self.curves[hand].extend(
                    plot.plot(
                        name=channel,
                        pen=pg.mkPen(colors[index], width=1),
                        autoDownsample=True,
                        downsampleMethod="peak",
                        connect="finite",
                    )
                    for index, channel in enumerate(channels)
                )
        self.window.addLabel(
            "bend.thumb[1] = dorsal (back of hand), not another thumb pad<br>"
            "IMU: last 5 s of host receipt time; magnetometer units unspecified",
            row=5,
            col=1,
            colspan=2,
        )
        for row, preferred, minimum in ((1, 210, 120), (2, 270, 160)):
            self.window.ci.layout.setRowPreferredHeight(row, preferred)
            self.window.ci.layout.setRowMinimumHeight(row, minimum)
            self.window.ci.layout.setRowStretchFactor(row, 1)
        self.window.ci.layout.setRowFixedHeight(3, 110)
        self.window.ci.layout.setRowFixedHeight(4, 210)

    def update(self) -> None:
        import numpy as np

        with self.capture.lock:
            latest = self.capture.latest.copy()
            counts = self.capture.counts.copy()
            history = {hand: list(samples) for hand, samples in self.capture.history.items()}
        now_ns = time.time_ns()
        for hand, frame in latest.items():
            age = max(0, now_ns - frame.host_timestamp_ns) / 1e9
            self.headers[hand].setText(f"{hand.upper()} | {counts[hand]:,} packets<br>frame age {age:.2f}s")
            image = np.full((4, 19), np.nan)
            for index, finger in enumerate(self.fingers):
                values = getattr(frame.tactile, finger)
                if values is not None:
                    image[:, 4 * index : 4 * index + 3] = values
            self.images[hand].setImage(image, autoLevels=False)
            self.images[hand].setOpacity(1 if age < 1 else 0.3)
            if frame.tactile.palm is not None:
                self.palms[hand].setImage(np.asarray(frame.tactile.palm, dtype=float), autoLevels=False)
            self.palms[hand].setOpacity(1 if age < 1 else 0.3)
            if frame.bend is not None:
                self.bars[hand].setOpts(
                    height=[value for finger in self.fingers for value in getattr(frame.bend, finger)]
                )
            self.bars[hand].setOpacity(1 if age < 1 else 0.3)
            samples = history.get(hand, [])
            if samples:
                points = np.asarray(samples)
                times = points[:, 0] - now_ns / 1e9
                for index, curve in enumerate(self.curves[hand], start=1):
                    curve.setData(times, points[:, index])

    def run(self, future: Future[None]) -> None:
        from pyqtgraph.Qt import QtCore

        error: Exception | None = None
        last_report = time.monotonic()

        def tick() -> None:
            nonlocal error, last_report
            try:
                self.update()
                if future.done():
                    self.app.quit()
                if time.monotonic() - last_report >= 1:
                    print(self.capture.status(), flush=True)
                    last_report = time.monotonic()
            except Exception as exc:  # noqa: BLE001 - re-raise Qt callback errors after the event loop exits.
                error = exc
                self.app.quit()

        timer = QtCore.QTimer(self.window)
        timer.timeout.connect(tick)
        previous_sigint = signal.signal(signal.SIGINT, lambda *_: self.app.quit())
        try:
            timer.start(40)  # 25 FPS target; acquisition has its own worker.
            self.window.show()
            self.app.exec()
        finally:
            timer.stop()
            self.capture.stop.set()
            self.window.close()
            signal.signal(signal.SIGINT, previous_sigint)
        if error is not None:
            raise error
