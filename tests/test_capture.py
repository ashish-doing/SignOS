import pytest

from src.perception.capture import Camera, CameraError, FpsMeter


def test_fps_meter_math():
    m = FpsMeter(window_s=1.0)
    fps = 0.0
    for i in range(31):
        fps = m.tick(now=i / 30)
    assert fps == pytest.approx(30.0, rel=0.05)


def test_camera_opens_and_reads():
    try:
        cam = Camera(0).open()
    except CameraError as e:
        pytest.skip(str(e))
    m, fps = FpsMeter(), 0.0
    try:
        for _ in range(60):
            frame = cam.read()
            fps = m.tick()
    finally:
        cam.release()
    print(f"\nMEASURED-LOCAL webcam fps: {fps:.1f}")
    assert frame.ndim == 3 and fps > 1.0