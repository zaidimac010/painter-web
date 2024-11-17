import sys
import cv2
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, QPushButton, 
                             QLabel, QColorDialog, QFileDialog, QVBoxLayout, QSlider,
                             QGraphicsDropShadowEffect, QMessageBox, QSizePolicy, QMenu, QButtonGroup, QFrame, QDialog, QListWidget, QTabWidget)
from PyQt6.QtGui import (QPainter, QPen, QColor, QIcon, QPixmap, QPainterPath, 
                         QImage)
from PyQt6.QtCore import Qt, QPointF, QSize, QSizeF, pyqtSignal, QPropertyAnimation, QEasingCurve, QRect, QTimer, QRectF, QUuid, QUrl, QObject, QThread
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
import time
import threading
import queue
import mss
import mss.tools
import numpy as np
import platform
import win32gui
import win32ui
import win32con 
from ctypes import windll
import psutil
import win32process
from typing import Optional, List, Tuple

# Define constants at the beginning of the file
MAX_FRAME_BUFFER_SIZE = 5
FRAME_RATE = 60  # Frames per second
FRAME_DURATION = 1.0 / FRAME_RATE
SEEK_COOLDOWN_MS = 50
SEEK_THRESHOLD_FRAMES = 1
MIN_BRUSH_SIZE = 2
MAX_BRUSH_SIZE = 50
HANDLE_SIZE = 10

class UploadedImage:
    def __init__(self, pixmap: QPixmap, position: QPointF, size: QSizeF) -> None:
        self.id = QUuid.createUuid()
        self.pixmap = pixmap
        self.position = position
        self.size = size
        self.selected = False

class VideoTimeline(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)  # Adjust spacing as needed
        
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)  # {{ edit_2 }}
        self.layout.addWidget(self.slider, 1)  # {{ edit_3 }} Add stretch factor for slider
        
        self.speaker_button = QPushButton(QIcon("icons/speaker.png"), "")
        self.speaker_button.setCheckable(True)
        self.speaker_button.setFixedSize(24, 24)
        self.speaker_button.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.9);
                border: none;
                border-radius: 12px;
            }
            QPushButton:checked {
                background: rgba(255, 255, 255, 0.95);
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 1);
            }
        """)
        self.layout.addWidget(self.speaker_button, 0)  # {{ edit_4 }} Add speaker button without stretch
        
        self.setFixedHeight(32)
        
        self.setStyleSheet("""
            QSlider::groove:horizontal {
                background: rgba(200, 200, 200, 0.8);
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #fff;
                border: 2px solid #3498db;
                width: 16px;
                height: 16px;
                margin-top: -6px;
                margin-bottom: -6px;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: #ecf0f1;
                border: 2px solid #2980b9;
            }
        """)

class VideoWorker(QObject):
    frame_ready: pyqtSignal = pyqtSignal(QPixmap)
    position_changed: pyqtSignal = pyqtSignal(int)

    def __init__(self, video_path: str, size: QSizeF) -> None:
        super().__init__()
        self.video_path = video_path
        self.cap = cv2.VideoCapture(video_path)
        if not self.cap.isOpened():
            raise ValueError(f"Cannot open video: {video_path}")
        
        # Get accurate FPS from video
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.fps <= 0 or self.fps > 120:  # Sanity check
            self.fps = 30.0  # Fallback to standard fps
        
        self.frame_duration = 1.0 / self.fps
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Initialize other variables
        self.running = True
        self.playing = False
        self.current_frame = 0
        self.size = size
        self.frame_buffer = queue.Queue(maxsize=MAX_FRAME_BUFFER_SIZE)
        self.decode_lock = threading.Lock()
        self.last_frame_time = None
        self.seek_requested = False
        self.seek_frame = 0
        
        # Frame timing control
        self.next_frame_time = 0
        
        # Initialize QThread
        self.thread = QThread()
        self.moveToThread(self.thread)
        self.thread.started.connect(self.process_video)
        self.thread.finished.connect(self.cleanup)
        self.thread.start()

    def process_video(self) -> None:
        error_count = 0
        MAX_ERRORS = 3
        RECOVERY_DELAY = 0.5

        while self.running:
            try:
                if self.seek_requested:
                    with self.decode_lock:
                        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.seek_frame)
                        self.current_frame = self.seek_frame
                        self.frame_buffer.queue.clear()
                        ret, frame = self.cap.read()
                        if ret:
                            pixmap = self.frame_to_pixmap(frame)
                            self.frame_ready.emit(pixmap)
                            self.position_changed.emit(self.current_frame)
                            error_count = 0
                            self.next_frame_time = time.perf_counter()  # Reset timing
                    self.seek_requested = False
                    continue

                if self.playing:
                    current_time = time.perf_counter()
                    
                    # Check if it's time for the next frame
                    if current_time >= self.next_frame_time:
                        with self.decode_lock:
                            ret, frame = self.cap.read()
                            if ret:
                                pixmap = self.frame_to_pixmap(frame)
                                self.frame_ready.emit(pixmap)
                                self.current_frame += 1
                                self.position_changed.emit(self.current_frame)
                                error_count = 0
                                
                                # Calculate next frame time based on original FPS
                                self.next_frame_time = current_time + self.frame_duration
                                
                                if self.current_frame >= self.total_frames:
                                    self.current_frame = 0
                                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                                    self.playing = False
                            else:
                                error_count += 1
                                if error_count >= MAX_ERRORS:
                                    print("Too many errors, stopping playback")
                                    self.playing = False
                                    break
                                time.sleep(RECOVERY_DELAY)
                    else:
                        # Sleep for a shorter duration to maintain responsiveness
                        sleep_time = min(0.001, (self.next_frame_time - current_time) / 2)
                        time.sleep(sleep_time)
                else:
                    time.sleep(0.01)  # Longer sleep when not playing

            except Exception as e:
                print(f"Error in video processing: {str(e)}")
                error_count += 1
                if error_count >= MAX_ERRORS:
                    print("Too many errors, stopping playback")
                    self.playing = False
                    break
                time.sleep(RECOVERY_DELAY)

    def frame_to_pixmap(self, frame: np.ndarray) -> QPixmap:
        """Convert frame to pixmap with proper scaling"""
        try:
            rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            qt_image = QImage(rgb_image.data, rgb_image.shape[1], rgb_image.shape[0], 
                             rgb_image.shape[1] * 3, QImage.Format.Format_RGB888)
            
            pixmap = QPixmap.fromImage(qt_image)
            if pixmap.isNull():
                return QPixmap()
            
            # Scale with high quality
            scaled_pixmap = pixmap.scaled(
                self.size.toSize(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            return scaled_pixmap
        
        except Exception as e:
            return QPixmap()

    def play(self) -> None:
        self.playing = True
        self.next_frame_time = time.perf_counter()  # Reset timing when starting playback

    def pause(self) -> None:
        self.playing = False

    def seek(self, frame: int) -> None:
        self.seek_requested = True
        self.seek_frame = frame

    def stop(self) -> None:
        self.running = False
        self.thread.quit()
        self.thread.wait()
        if self.cap.isOpened():
            self.cap.release()

    def cleanup(self) -> None:
        """Ensure proper cleanup of video resources."""
        try:
            self.running = False
            if self.cap.isOpened():
                self.cap.release()
        except Exception as e:
            pass

class UploadedVideo:
    def __init__(self, video_path, position, size):
        self.id = QUuid.createUuid()
        self.video_path = video_path
        self.position = position
        self.size = size
        self.selected = False
        
        # Initialize video capture
        self.cap = cv2.VideoCapture(video_path)
        if not self.cap.isOpened():
            QMessageBox.critical(None, "Video Load Error", f"Failed to load video: {video_path}")
            return
        
        # Get video properties
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.fps = self.fps if self.fps > 0 else 30
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.current_frame = 0
        self.playing = False
        
        # Initialize timeline
        self.timeline = VideoTimeline()
        self.timeline.slider.setRange(0, self.frame_count - 1)
        self.timeline.slider.setPageStep(1)
        self.timeline.hide()  # Initially hide the timeline
        
        # Set timeline z-order to be above everything
        self.timeline.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, True)
        self.timeline.raise_()  # Ensure timeline is on top
        
        # Initialize video display
        self.current_pixmap = QPixmap(int(self.size.width()), int(self.size.height()))
        
        # Create and setup the worker thread first
        self.thread = QThread()
        self.worker = VideoWorker(video_path, self.size)
        
        # Move worker to thread before connecting signals
        self.worker.moveToThread(self.thread)
        
        # Connect signals after moving to thread
        self.worker.frame_ready.connect(self.update_frame)
        self.worker.position_changed.connect(self.update_position)
        
        # Start the thread
        self.thread.started.connect(self.worker.process_video)
        self.thread.start()

        try:
            # Set up audio with error handling
            self.media_player = QMediaPlayer()
            self.audio_output = QAudioOutput()
            self.media_player.setAudioOutput(self.audio_output)
            self.media_player.setSource(QUrl.fromLocalFile(video_path))
            self.volume = 1.0
            self.audio_output.setVolume(self.volume)
        except Exception as e:
            print(f"Audio initialization error: {e}")
            # Continue without audio if it fails
            self.media_player = None
            self.audio_output = None

        # Connect signals
        self.timeline.slider.valueChanged.connect(self.on_slider_value_changed)
        self.timeline.slider.sliderPressed.connect(self.on_slider_pressed)
        self.timeline.slider.sliderReleased.connect(self.on_slider_released)
        self.timeline.speaker_button.clicked.connect(self.toggle_mute)
        
        # Connect media signals only if media player is available
        if self.media_player:
            self.media_player.positionChanged.connect(self.sync_video_position)
            self.media_player.positionChanged.connect(self.on_media_position_changed)
            self.media_player.durationChanged.connect(self.on_media_duration_changed)
        
        # State flags
        self.slider_being_dragged = False
        self.seek_cooldown = 50
        self.last_seek_time = 0
        self.seek_threshold = 1

    def update_position(self, frame: int) -> None:
        """Update timeline position when video frame changes."""
        if not self.slider_being_dragged:
            self.timeline.slider.blockSignals(True)
            self.timeline.slider.setValue(frame)
            self.timeline.slider.blockSignals(False)
            self.current_frame = frame

    def seek(self, frame):
        current_time = time.time() * 1000
        if current_time - self.last_seek_time < self.seek_cooldown:
            return

        frame = max(0, min(frame, self.frame_count - 1))
        self.worker.seek(frame)
        position = int(frame / self.fps * 1000)
        self.media_player.setPosition(position)
        self.current_frame = frame
        self.last_seek_time = current_time

    def play_pause(self) -> None:
        self.playing = not self.playing
        if self.playing:
            current_frame = self.timeline.slider.value()
            self.seek(current_frame)
            self.worker.play()
            if self.media_player:
                self.media_player.play()
        else:
            self.worker.pause()
            if self.media_player:
                self.media_player.pause()
            self.worker.last_frame_time = None

    def update_frame(self, pixmap):
        self.current_pixmap = pixmap
        if not self.slider_being_dragged:
            self.timeline.slider.setValue(self.current_frame)
        if hasattr(self, 'canvas'):
            self.canvas.update()

    def toggle_mute(self):
        if not self.audio_output:
            return
        if self.audio_output.isMuted():
            self.audio_output.setMuted(False)
            self.timeline.speaker_button.setIcon(QIcon("icons/speaker.png"))
        else:
            self.audio_output.setMuted(True)
            self.timeline.speaker_button.setIcon(QIcon("icons/muted.png"))

    def set_volume(self, volume):
        self.volume = volume
        self.audio_output.setVolume(volume)

    def set_duration(self, total_frames):
        self.frame_count = total_frames
        self.timeline.slider.setRange(0, total_frames - 1)

    def update_frame_from_current(self):
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
        ret, frame = self.cap.read()
        if ret:
            pixmap = self.worker.frame_to_pixmap(frame)
            self.current_pixmap = pixmap
            if hasattr(self, 'canvas'):
                self.canvas.update()

    def resize(self, new_size):
        self.size = new_size
        self.worker.size = new_size
        self.update_timeline_position()  # {{ edit_7 }} Ensure timeline is repositioned
        self.update_frame_position(self.current_frame)  # Update frame position

    def update_timeline_position(self):
        """Update timeline position and visibility with improved positioning"""
        if not hasattr(self, 'timeline'):
            return
        
        # Calculate timeline position to be at bottom of video
        timeline_width = int(self.size.width())
        timeline_x = int(self.position.x())
        timeline_y = int(self.position.y() + self.size.height() - self.timeline.height())

        # Add padding to prevent timeline from touching video edges
        PADDING = 4
        timeline_width = max(100, timeline_width - (2 * PADDING))
        timeline_x += PADDING
        timeline_y -= PADDING

        # Update the geometry of the timeline
        self.timeline.setGeometry(
            timeline_x,
            timeline_y,
            timeline_width,
            self.timeline.height()
        )

        # Show/hide timeline based on selection state
        if self.selected:
            self.timeline.show()
            self.timeline.raise_()  # Ensure timeline is visible above other elements
        else:
            self.timeline.hide()

    def update_frame_position(self, frame: int) -> None:
        """Update timeline slider position when video frame changes."""
        if not self.slider_being_dragged:
            self.timeline.slider.blockSignals(True)
            self.timeline.slider.setValue(frame)
            self.timeline.slider.blockSignals(False)
            self.current_frame = frame

    def sync_video_position(self, position):
        """Synchronize video frames with audio position"""
        try:
            if not self.slider_being_dragged and self.media_player.duration() > 0:
                # Calculate frame number from position
                frame = int((position / self.media_player.duration()) * self.frame_count)
                
                # Only seek if the difference is significant
                if abs(frame - self.current_frame) >= self.seek_threshold:
                    self.worker.seek(frame)
        except Exception as e:
            pass

    def cleanup(self):
        """Enhanced cleanup with proper resource management"""
        try:
            # Stop playback first
            self.playing = False
            
            # Clean up video worker
            if hasattr(self, 'worker'):
                try:
                    self.worker.frame_ready.disconnect()
                    self.worker.position_changed.disconnect()
                except Exception:
                    pass
                self.worker.stop()

            # Clean up media player
            if hasattr(self, 'media_player') and self.media_player:
                try:
                    self.media_player.stop()
                except Exception:
                    pass
                self.media_player = None

            # Clean up timeline
            if hasattr(self, 'timeline'):
                self.timeline.setParent(None)
                self.timeline.deleteLater()

            # Clean up thread
            if hasattr(self, 'thread') and self.thread.isRunning():
                self.thread.quit()
                if not self.thread.wait(1000):
                    self.thread.terminate()
                self.thread = None

            # Clean up video capture
            if hasattr(self, 'cap') and self.cap.isOpened():
                self.cap.release()
                self.cap = None

        except Exception as e:
            print(f"Error during cleanup: {str(e)}")
        finally:
            self.worker = None
            self.timeline = None

    # Add these missing methods
    def on_slider_pressed(self):
        """Called when user starts dragging the slider"""
        self.slider_being_dragged = True
        if self.playing:
            self.worker.pause()
            self.media_player.pause()

    def on_slider_released(self):
        """Called when user releases the slider"""
        self.slider_being_dragged = False
        if self.playing:
            self.worker.play()
            self.media_player.play()
        self.seek(self.timeline.slider.value())

    def on_slider_value_changed(self, value):
        """Called when slider value changes"""
        if self.slider_being_dragged:
            self.seek(value)

    def on_media_position_changed(self, position):
        """Called when media player position changes"""
        if not self.slider_being_dragged and self.media_player.duration() > 0:
            # Calculate frame number from position
            frame = int((position / self.media_player.duration()) * self.frame_count)
            
            # Only seek if the difference is significant
            if abs(frame - self.current_frame) >= self.seek_threshold:
                self.worker.seek(frame)

    def on_media_duration_changed(self, duration):
        """Called when media duration is available"""
        total_frames = int(duration / 1000 * self.fps)
        self.timeline.slider.setRange(0, total_frames - 1)

# Add this helper class for window selection
class WindowSelector:
    def __init__(self) -> None:
        self.windows: List[Tuple[int, str, str]] = []

    def enum_window_callback(self, hwnd: int, _) -> None:
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            window_text = win32gui.GetWindowText(hwnd)
            if not window_text or window_text.isspace():
                return
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            if (not (style & win32con.WS_VISIBLE) or
                (ex_style & win32con.WS_EX_TOOLWINDOW) or
                (ex_style & win32con.WS_EX_LAYERED and not (style & win32con.WS_CHILD))):
                return
            try:
                rect = win32gui.GetWindowRect(hwnd)
                if rect[2] - rect[0] <= 0 or rect[3] - rect[1] <= 0:
                    return
            except:
                return
            class_name = win32gui.GetClassName(hwnd)
            skip_classes = {
                'Windows.UI.Core.CoreWindow',
                'ApplicationFrameWindow',
                'Windows.UI.Input.InputSite',
                'Progman',
                'Shell_TrayWnd',
                'DV2ControlHost',
            }
            if class_name in skip_classes:
                return
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                process = psutil.Process(pid)
                process_name = process.name().lower()
                skip_processes = {
                    'shellexperiencehost.exe',
                    'searchui.exe',
                    'searchapp.exe',
                }
                if process_name in skip_processes:
                    return
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            self.windows.append((hwnd, window_text, class_name))
        except Exception as e:
            pass

    def get_window_list(self) -> List[Tuple[int, str, str]]:
        self.windows = []
        win32gui.EnumWindows(self.enum_window_callback, None)
        self.windows.sort(key=lambda x: x[1].lower())
        return self.windows

    def get_browser_windows(self) -> List[Tuple[int, str, str]]:
        """Retrieve browser windows instead of individual tabs."""
        browser_windows: List[Tuple[int, str, str]] = []
        browsers = {
            'Google Chrome': 'chrome.exe',
            'Mozilla Firefox': 'firefox.exe',
            'Microsoft Edge': 'msedge.exe'
        }
        for hwnd, title, class_name in self.get_window_list():
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                process = psutil.Process(pid)
                process_name = process.name().lower()
                if process_name in browsers.values():
                    if title:
                        browser_windows.append((hwnd, title, class_name))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return browser_windows

# Update the ScreenCaptureWorker class's capture methods

class ScreenCaptureWorker(QObject):
    frame_ready = pyqtSignal(QPixmap)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, monitor=None, window_id=None):
        super().__init__()
        self.running = True
        self.capturing = False
        self.monitor = monitor
        self.window_id = window_id
        self.system = platform.system()
        self.last_capture_time = 0
        self.frame_interval = 1/60  # Target 60 FPS
        self.target_size = None
        self.frame_buffer = queue.Queue(maxsize=2)  # Small buffer for smoothness
        self.last_frame_time = 0
        self.skip_frame_threshold = 1000/30  # Skip frames if processing takes longer than 33ms
        self.capture_method = self._determine_capture_method()

        # Initialize last_error_time and error_cooldown for rate-limiting errors
        self.last_error_time = 0
        self.error_cooldown = 1  # seconds
            
    def _determine_capture_method(self):
        """Select the most efficient capture method based on OS and scenario"""
        if self.system == 'Windows':
            if self.window_id:
                return 'win32'
            return 'mss'
        return 'mss'  # Default to mss for other platforms

    def set_target_size(self, size):
        """Set target size and calculate scaling factors"""
        self.target_size = size
        self.update_scaling_factors()

    def update_scaling_factors(self):
        """Calculate optimal scaling factors for high quality output"""
        if not self.target_size:
            return
            
        if self.window_id:
            try:
                rect = win32gui.GetWindowRect(self.window_id)
                self.source_width = rect[2] - rect[0]
                self.source_height = rect[3] - rect[1]
            except:
                return
        elif self.monitor:
            self.source_width = self.monitor['width']
            self.source_height = self.monitor['height']
        else:
            return

        # Calculate aspect ratios
        source_aspect = self.source_width / self.source_height
        target_aspect = self.target_size.width() / self.target_size.height()

        # Use 100% of available space while maintaining aspect ratio
        if source_aspect > target_aspect:
            self.scaled_width = int(self.target_size.width())
            self.scaled_height = int(self.target_size.width() / source_aspect)
        else:
            self.scaled_height = int(self.target_size.height())
            self.scaled_width = int(self.target_size.height() * source_aspect)

        # Ensure minimum dimensions
        self.scaled_width = max(100, self.scaled_width)
        self.scaled_height = max(100, self.scaled_height)

    def capture_screen(self):
        try:
            if self.capture_method == 'win32':
                self.capture_window_loop()
            else:
                with mss.mss() as sct:
                    # Configure mss for better performance
                    sct.compression_level = 2  # Lower compression for better speed
                    self.capture_monitor_loop(sct)
        except Exception as e:
            self.emit_error(f"Screen capture error: {str(e)}")
            self.stop()

    def capture_window_loop(self):
        # Initialize DC resources
        self.dc_resources = {'hwndDC': None, 'mfcDC': None, 'saveDC': None, 'saveBitMap': None}
        
        try:
            windll.user32.SetProcessDPIAware()
            
            while self.running:
                if not self.capturing:
                    time.sleep(0.1)
                    continue

                current_time = time.perf_counter()
                if current_time - self.last_frame_time < self.frame_interval:
                    time.sleep(0.001)  # Short sleep to prevent CPU overuse
                    continue

                if not win32gui.IsWindow(self.window_id):
                    self.emit_error("Window no longer exists")
                    break

                try:
                    # Capture frame
                    pixmap = self.capture_window_frame()
                    if pixmap and not pixmap.isNull():
                        self.frame_ready.emit(pixmap)
                        self.last_frame_time = current_time

                except Exception as e:
                    print(f"Frame capture error: {str(e)}")
                    time.sleep(0.1)

        finally:
            self.cleanup_dc_resources()

    def capture_window_frame(self):
        """High quality window capture method"""
        try:
            # Get window dimensions
            rect = win32gui.GetWindowRect(self.window_id)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]

            if width <= 0 or height <= 0:
                return None

            # Initialize DC resources
            hwndDC = win32gui.GetWindowDC(self.window_id)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)

            # Use PrintWindow with PW_RENDERFULLCONTENT flag for better quality
            result = windll.user32.PrintWindow(self.window_id, saveDC.GetSafeHdc(), 3)
            if result:
                bmpinfo = saveBitMap.GetInfo()
                bmpstr = saveBitMap.GetBitmapBits(True)

                # Create high quality QImage
                qimage = QImage(
                    bmpstr,
                    width,
                    height,
                    QImage.Format.Format_ARGB32_Premultiplied
                )

                # Scale with high quality
                if self.target_size:
                    qimage = qimage.scaled(
                        self.target_size.width(),
                        self.target_size.height(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )

                pixmap = QPixmap.fromImage(qimage)
                return pixmap

            return None

        finally:
            # Cleanup DC resources
            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            win32gui.ReleaseDC(self.window_id, hwndDC)
            win32gui.DeleteObject(saveBitMap.GetHandle())

    def capture_monitor_loop(self, sct):
        """Optimized monitor capture loop"""
        try:
            monitor = self.monitor if self.monitor else sct.monitors[1]
            last_frame_time = time.perf_counter()
            frame_interval = 1.0 / 60  # Target 60 FPS

            while self.running:
                if not self.capturing:
                    time.sleep(0.1)
                    continue

                current_time = time.perf_counter()
                if current_time - last_frame_time < frame_interval:
                    time.sleep(0.001)  # Short sleep to prevent CPU overuse
                    continue

                # Capture and process frame
                screenshot = sct.grab(monitor)
                img = np.array(screenshot)

                # Convert to QImage efficiently
                qimage = QImage(
                    img.data,
                    img.shape[1],
                    img.shape[0],
                    img.shape[1] * 3,
                    QImage.Format.Format_RGB888
                )

                if not qimage.isNull():
                    pixmap = QPixmap.fromImage(qimage)
                    if not pixmap.isNull() and self.target_size:
                        pixmap = pixmap.scaled(
                            self.target_size.width(),
                            self.target_size.height(),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation
                        )
                        self.frame_ready.emit(pixmap)

                last_frame_time = current_time

        except Exception as e:
            self.error_occurred.emit(f"Monitor capture error: {e}")

    def scale_pixmap(self, pixmap, target_size):
        """Scale pixmap while maintaining aspect ratio with high quality"""
        if pixmap.isNull():
            return pixmap

        # Get source and target dimensions
        src_width = pixmap.width()
        src_height = pixmap.height()
        target_width = target_size.width()
        target_height = target_size.height()

        # Calculate scaling factors
        width_ratio = target_width / src_width
        height_ratio = target_height / src_height
        
        # Use the smaller ratio to fit within bounds while maintaining aspect ratio
        scale_factor = min(width_ratio, height_ratio)
        
        new_width = int(src_width * scale_factor)
        new_height = int(src_height * scale_factor)

        # Create a high-quality scaled pixmap
        scaled_pixmap = pixmap.scaled(
            new_width,
            new_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        return scaled_pixmap

    def emit_error(self, message):
        current_time = time.time()
        if current_time - self.last_error_time >= self.error_cooldown:
            self.error_occurred.emit(message)
            self.last_error_time = current_time
    
    def start_capture(self):
        self.capturing = True
    
    def stop_capture(self):
        self.capturing = False
    
    def stop(self) -> None:
        """Ensure proper cleanup when stopping."""
        self.running = False
        self.capturing = False
        try:
            # Additional cleanup if necessary
            self.emit_error("Screen capture worker stopped successfully.")
        except Exception as e:
            pass

    def cleanup_dc_resources(self):
        """Clean up DC resources safely"""
        try:
            if self.dc_resources['saveDC']:
                self.dc_resources['saveDC'].DeleteDC()
            if self.dc_resources['mfcDC']:
                self.dc_resources['mfcDC'].DeleteDC()
            if self.dc_resources['hwndDC'] and self.window_id:
                win32gui.ReleaseDC(self.window_id, self.dc_resources['hwndDC'])
            if self.dc_resources['saveBitMap']:
                win32gui.DeleteObject(self.dc_resources['saveBitMap'].GetHandle())
        except Exception as e:
            print(f"Error cleaning up DC resources: {e}")

class Canvas(QWidget):
    color_changed = pyqtSignal(QColor)

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StaticContents)
        self.drawing = False
        self.last_point = QPointF()
        self.color = QColor(Qt.GlobalColor.black)
        self.brush_size = 2
        self.tool = "pen"
        self.pixmap = QPixmap(3000, 2000)
        self.pixmap.fill(Qt.GlobalColor.white)
        self.undo_stack = []
        self.redo_stack = []
        self.smoothing_factor = 0.3
        self.drawing_layer = QPixmap(3000, 2000)
        self.drawing_layer.fill(Qt.GlobalColor.transparent)
        self.last_update_rect = QRectF()
        self.hover_pos = QPointF()
        self.setMouseTracking(True)  # Enable mouse tracking
        self.setCursor(Qt.CursorShape.BlankCursor)  # Hide the default cursor

        # Add a layout to the Canvas
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)

        self.uploaded_items = []  # This will store both images and videos in order
        self.resizing = False
        self.dragging = False
        self.resize_handle_size = 10
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # Enable focus for the canvas

        self.current_shape = None  # {{ edit_1 }} Track the current shape being drawn
        self.shapes = []  # {{ edit_2 }} Store drawn shapes for rendering and undo/redo

    def resizeEvent(self, event):
        if self.pixmap.size().width() < self.size().width() or self.pixmap.size().height() < self.size().height():
            new_pixmap = QPixmap(max(self.pixmap.size().width(), self.size().width()),
                                 max(self.pixmap.size().height(), self.size().height()))
            new_pixmap.fill(Qt.GlobalColor.white)
            painter = QPainter(new_pixmap)
            painter.drawPixmap(0, 0, self.pixmap)
            self.pixmap = new_pixmap

        # Update the layout to ensure proper resizing
        self.layout.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        update_rect = event.rect()
        painter.drawPixmap(update_rect, self.pixmap, update_rect)

        # Draw shapes
        for shape in self.shapes:
            self.draw_shape(painter, shape)

        # Draw current shape if any
        if self.current_shape:
            self.draw_shape(painter, self.current_shape, preview=True)

        # Draw items in order of their position in uploaded_items list
        # This ensures proper z-order for both images and videos
        for item in self.uploaded_items:
            if isinstance(item, UploadedVideo):
                # Update timeline position before drawing video
                item.timeline.setParent(self)
                item.timeline.move(
                    int(item.position.x()),
                    int(item.position.y() + item.size.height() - item.timeline.height())
                )  # Added missing closing parenthesis
                if item.selected:
                    item.timeline.show()
                    item.timeline.raise_()
                else:
                    item.timeline.hide()
                self.draw_video(painter, item)
            elif isinstance(item, UploadedImage):
                self.draw_image(painter, item)

        painter.drawPixmap(update_rect, self.drawing_layer, update_rect)

        # Draw hover circle on top
        if self.tool in ["pen", "eraser", "rectangle", "ellipse", "line"]:
            painter.setPen(QPen(QColor(50, 50, 50), 2, Qt.PenStyle.SolidLine))
            painter.setBrush(QColor(200, 200, 200, 100))
            painter.drawEllipse(self.hover_pos, self.brush_size / 2, self.brush_size / 2)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            
            # Hide size slider if it's visible
            if hasattr(self.window(), 'size_slider') and self.window().size_slider.isVisible():
                # Check if click is outside the slider
                slider = self.window().size_slider
                slider_geo = slider.geometry()
                if not slider_geo.contains(event.position().toPoint()):
                    slider.hide()
            
            # Deselect all items first
            for item in self.uploaded_items:
                item.selected = False
                if isinstance(item, UploadedVideo):
                    item.update_timeline_position()  # Update position and visibility
                    item.update_frame_position(item.current_frame)  # Update frame position
            
            # Check items in reverse order (top to bottom)
            for item in reversed(self.uploaded_items):
                if ((isinstance(item, UploadedVideo) and self.is_over_video(pos, item)) or 
                    (isinstance(item, UploadedImage) and self.is_over_image(pos, item))):
                    item.selected = True
                    if isinstance(item, UploadedVideo):
                        item.update_timeline_position()  # Update position and visibility
                        item.update_frame_position(item.current_frame)  # Update frame position
                    if self.is_over_resize_handle(pos, item):
                        self.resizing = True
                        self.selected_handle = self.get_resize_handle(pos, item)
                        self.selected_video = item if isinstance(item, UploadedVideo) else None
                        self.selected_image = item if isinstance(item, UploadedImage) else None
                    else:
                        self.dragging = True
                        self.drag_start_pos = pos - item.position
                        self.selected_video = item if isinstance(item, UploadedVideo) else None
                        self.selected_image = item if isinstance(item, UploadedImage) else None
                    break
            
            if not self.resizing and not self.dragging:
                self.drawing = True
                self.last_point = pos
                self.undo_stack.append(self.drawing_layer.copy())
                self.redo_stack.clear()
                if len(self.undo_stack) > 20:
                    self.undo_stack.pop(0)

            # Initialize shape drawing
            if self.tool in ["rectangle", "ellipse", "line"]:
                self.drawing = True
                self.start_point = pos
                self.current_shape = {"type": self.tool, "start": pos, "end": pos, "color": self.color, "size": self.brush_size}
                self.undo_stack.append(self.shapes.copy())  # {{ edit_3 }} Record state for undo
                self.redo_stack.clear()
                return  # {{ edit_4 }} Prevent further processing when drawing shapes

        elif event.button() == Qt.MouseButton.RightButton:
            self.handle_right_click(event)

        self.update()

    def mouseDoubleClickEvent(self, event):
        pos = event.position()
        for video in self.uploaded_items:
            if isinstance(video, UploadedVideo) and self.is_over_video(pos, video):
                print("Double-clicked on video")
                video.play_pause()
                break

    def mouseMoveEvent(self, event):
        self.hover_pos = event.position()
        
        # Default cursor
        cursor = Qt.CursorShape.ArrowCursor
        
        # Check for resize handles and set appropriate cursor
        for item in reversed(self.uploaded_items):
            if ((isinstance(item, UploadedVideo) and self.is_over_video(self.hover_pos, item)) or 
                (isinstance(item, UploadedImage) and self.is_over_image(self.hover_pos, item))):
                
                # Check if near any resize handle
                handle = self.get_resize_handle(self.hover_pos, item)
                if handle is not None:
                    # Set resize cursor based on handle position
                    if handle == 0:  # top-left
                        cursor = Qt.CursorShape.SizeFDiagCursor
                    elif handle == 1:  # top-right
                        cursor = Qt.CursorShape.SizeBDiagCursor
                    elif handle == 2:  # bottom-left
                        cursor = Qt.CursorShape.SizeBDiagCursor
                    elif handle == 3:  # bottom-right
                        cursor = Qt.CursorShape.SizeFDiagCursor
                else:
                    # If over item but not over handle, show move cursor
                    cursor = Qt.CursorShape.SizeAllCursor
                break
        
        # Only show blank cursor for drawing tools when not over any item
        if self.tool in ["pen", "eraser", "rectangle", "ellipse", "line"] and cursor == Qt.CursorShape.ArrowCursor:
            cursor = Qt.CursorShape.BlankCursor
            
        self.setCursor(cursor)

        if event.buttons() & Qt.MouseButton.LeftButton:
            if self.drawing:
                self.draw_on_canvas(event.position())
            elif self.resizing and (self.selected_video or self.selected_image):
                self.resize_item(event.position())
                # Update timeline position after resizing if it's a video
                if self.selected_video:
                    self.selected_video.update_timeline_position()
            elif self.dragging and (self.selected_video or self.selected_image):
                new_pos = event.position() - self.drag_start_pos
                if self.selected_video:
                    self.selected_video.position = new_pos
                    self.selected_video.update_timeline_position()
                elif self.selected_image:
                    self.selected_image.position = new_pos
                self.update()

        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drawing = False
            self.resizing = False
            self.dragging = False
            self.last_update_rect = QRectF()

        self.update()

    def draw_on_canvas(self, position):
        painter = QPainter(self.drawing_layer)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if self.tool == "pen":
            self.draw_smooth_line(painter, self.last_point, position, self.color)
        elif self.tool == "eraser":
            self.erase_smooth_line(painter, self.last_point, position)

        update_rect = QRectF(self.last_point, position).normalized()
        update_rect = update_rect.adjusted(-self.brush_size, -self.brush_size, self.brush_size, self.brush_size)
        self.last_update_rect = self.last_update_rect.united(update_rect)
        self.update(self.last_update_rect.toRect())
        self.last_point = position

    def draw_smooth_line(self, painter, start, end, color):
        path = QPainterPath()
        path.moveTo(start)
        
        # Calculate control points
        ctrl1 = QPointF(start.x() + (end.x() - start.x()) / 3,
                        start.y() + (end.y() - start.y()) / 3)
        ctrl2 = QPointF(start.x() + 2 * (end.x() - start.x()) / 3,
                        start.y() + 2 * (end.y() - start.y()) / 3)
        
        path.cubicTo(ctrl1, ctrl2, end)
        
        pen = QPen(color, self.brush_size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawPath(path)
        
        self.last_point = end

    def erase_smooth_line(self, painter, start, end):
        path = QPainterPath()
        path.moveTo(start)
        
        # Calculate control points
        ctrl1 = QPointF(start.x() + (end.x() - start.x()) / 3,
                        start.y() + (end.y() - start.y()) / 3)
        ctrl2 = QPointF(start.x() + 2 * (end.x() - start.x()) / 3,
                        start.y() + 2 * (end.y() - start.y()) / 3)
        
        path.cubicTo(ctrl1, ctrl2, end)

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        pen = QPen(Qt.GlobalColor.transparent, self.brush_size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawPath(path)
        
        self.last_point = end

    def set_color(self, color):
        self.color = color
        self.color_changed.emit(color)

    def clear(self):
        self.drawing_layer.fill(Qt.GlobalColor.transparent)
        self.update()

    def leaveEvent(self, event):
        self.hover_pos = QPointF()
        self.update()
        self.setCursor(Qt.CursorShape.ArrowCursor)  # Show default cursor when leaving the canvas

    def enterEvent(self, event):
        self.setCursor(Qt.CursorShape.BlankCursor)  # Hide cursor when entering the canvas

    def is_over_image(self, pos, image):
        return QRectF(image.position, image.size).contains(pos)

    def is_over_video(self, pos, video):
        video_rect = QRectF(video.position, video.size)
        return video_rect.contains(pos)

    def is_over_resize_handle(self, pos, item):
        """Get resize handle with increased sensitivity area"""
        # Increase handle detection area
        HANDLE_SENSITIVITY = HANDLE_SIZE * 2  # Double the handle detection area
        
        corners = self.get_item_corners(item)
        for i, corner in enumerate(corners):
            handle_rect = QRectF(
                corner.x() - HANDLE_SENSITIVITY/2,
                corner.y() - HANDLE_SENSITIVITY/2,
                HANDLE_SENSITIVITY,
                HANDLE_SENSITIVITY
            )
            if handle_rect.contains(pos):
                return i
        return None

    def get_item_corners(self, item):
        return [
            item.position,
            item.position + QPointF(item.size.width(), 0),
            item.position + QPointF(0, item.size.height()),
            item.position + QPointF(item.size.width(), item.size.height())
        ]

    def get_resize_handle(self, pos, item):
        """Get resize handle with increased sensitivity area"""
        # Increase handle detection area
        HANDLE_SENSITIVITY = HANDLE_SIZE * 2  # Double the handle detection area
        
        corners = self.get_item_corners(item)
        for i, corner in enumerate(corners):
            handle_rect = QRectF(
                corner.x() - HANDLE_SENSITIVITY/2,
                corner.y() - HANDLE_SENSITIVITY/2,
                HANDLE_SENSITIVITY,
                HANDLE_SENSITIVITY
            )
            if handle_rect.contains(pos):
                return i
        return None

    def get_resize_cursor(self, handle):
        if handle in [0, 3]:  # top-left, bottom-right
            return Qt.CursorShape.SizeFDiagCursor
        elif handle in [1, 2]:  # top-right, bottom-left
            return Qt.CursorShape.SizeBDiagCursor
        return Qt.CursorShape.SizeAllCursor

    def resize_item(self, pos):
        """Handle resizing of videos and images while maintaining aspect ratio and minimum size"""
        item = self.selected_video or self.selected_image
        if not item:
            return

        # Get original aspect ratio
        if isinstance(item, UploadedImage):
            aspect_ratio = item.pixmap.width() / item.pixmap.height()
        else:  # UploadedVideo
            aspect_ratio = item.current_pixmap.width() / item.current_pixmap.height()

        # Calculate minimum dimensions (maintain aspect ratio)
        MIN_WIDTH = 100
        MIN_HEIGHT = MIN_WIDTH / aspect_ratio

        # Calculate new dimensions based on handle position
        if self.selected_handle == 0:  # top-left
            # Calculate width based on x-movement
            new_width = max(MIN_WIDTH, item.position.x() + item.size.width() - pos.x())
            # Calculate height maintaining aspect ratio
            new_height = new_width / aspect_ratio
            
            if new_width >= MIN_WIDTH and new_height >= MIN_HEIGHT:
                # Update position and size
                new_x = pos.x()
                new_y = item.position.y() + item.size.height() - new_height
                item.position = QPointF(new_x, new_y)
                item.size = QSizeF(new_width, new_height)

        elif self.selected_handle == 1:  # top-right
            # Calculate width based on x-movement
            new_width = max(MIN_WIDTH, pos.x() - item.position.x())
            # Calculate height maintaining aspect ratio
            new_height = new_width / aspect_ratio
            
            if new_width >= MIN_WIDTH and new_height >= MIN_HEIGHT:
                # Update position and size (only y position changes)
                new_y = item.position.y() + item.size.height() - new_height
                item.position.setY(new_y)
                item.size = QSizeF(new_width, new_height)

        elif self.selected_handle == 2:  # bottom-left
            # Calculate width based on x-movement
            new_width = max(MIN_WIDTH, item.position.x() + item.size.width() - pos.x())
            # Calculate height maintaining aspect ratio
            new_height = new_width / aspect_ratio
            
            if new_width >= MIN_WIDTH and new_height >= MIN_HEIGHT:
                # Update position and size (only x position changes)
                new_x = pos.x()
                item.position.setX(new_x)
                item.size = QSizeF(new_width, new_height)

        elif self.selected_handle == 3:  # bottom-right
            # Calculate width based on x-movement
            new_width = max(MIN_WIDTH, pos.x() - item.position.x())
            # Calculate height maintaining aspect ratio
            new_height = new_width / aspect_ratio
            
            if new_width >= MIN_WIDTH and new_height >= MIN_HEIGHT:
                # Update size (position stays the same)
                item.size = QSizeF(new_width, new_height)

        # Update video-specific properties
        if isinstance(item, UploadedVideo):
            item.worker.size = item.size  # Update worker size
            item.update_timeline_position()  # Update timeline position

        self.update()

    def add_uploaded_image(self, image_path):
        try:
            pixmap = QPixmap(image_path)
            if pixmap.isNull():
                QMessageBox.critical(None, "Error", f"Failed to load image: {image_path}")
                return
            
            aspect_ratio = pixmap.width() / pixmap.height()
            max_size = 200

            if pixmap.width() > pixmap.height():
                new_width = min(pixmap.width(), max_size)
                new_height = new_width / aspect_ratio
            else:
                new_height = min(pixmap.height(), max_size)
                new_width = new_height * aspect_ratio

            position = QPointF(100, 100)
            size = QSizeF(new_width, new_height)
            
            new_image = UploadedImage(pixmap, position, size)
            new_image.selected = True
            self.uploaded_items.append(new_image)
            self.selected_image = new_image
            
            # Deselect other items
            for item in self.uploaded_items[:-1]:
                item.selected = False
                if isinstance(item, UploadedVideo):
                    item.timeline.hide()
            
            self.update()
            
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Error loading image: {str(e)}")

    def add_uploaded_video(self, video_path):
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                QMessageBox.critical(None, "Error", f"Failed to load video: {video_path}")
                return
            
            # Get video dimensions
            video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            aspect_ratio = video_width / video_height
            cap.release()
            
            # Set initial size while maintaining aspect ratio
            target_width = 320  # Base width
            target_height = int(target_width / aspect_ratio)
            
            position = QPointF(200, 200)
            size = QSizeF(target_width, target_height)
            
            new_video = UploadedVideo(video_path, position, size)
            new_video.canvas = self  # Set the canvas reference
            self.uploaded_items.append(new_video)
            
            new_video.update_timeline_position()
            new_video.timeline.setParent(self)  # Set the canvas as parent
            new_video.timeline.show()
            new_video.selected = True
            self.selected_video = new_video
            
            # Deselect other items
            for item in self.uploaded_items[:-1]:
                item.selected = False
                
            self.update()
            
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Error loading video: {str(e)}")

    def bring_item_to_front(self, item):
        """Bring item to front while maintaining proper z-order for both images and videos"""
        if item in self.uploaded_items:
            # Remove the item from the list
            self.uploaded_items.remove(item)
            
            # Add it back at the end (top)
            self.uploaded_items.append(item)
            
            # Select the brought-to-front item and deselect others
            for uploaded_item in self.uploaded_items:
                uploaded_item.selected = (uploaded_item == item)
                
                # Handle video timelines
                if isinstance(uploaded_item, UploadedVideo):
                    if uploaded_item.timeline:
                        # Ensure timeline is a child of the canvas
                        uploaded_item.timeline.setParent(self)
                        
                        if uploaded_item == item:
                            # Move selected video's timeline to top and show it
                            uploaded_item.timeline.raise_()
                            uploaded_item.timeline.show()
                        else:
                            # Stack other timelines and hide them
                            uploaded_item.timeline.stackUnder(self)
                            uploaded_item.timeline.hide()
                        
                        # Update timeline position
                        uploaded_item.update_timeline_position()
            
            # Update selected item references
            if isinstance(item, UploadedVideo):
                self.selected_video = item
                self.selected_image = None
            else:
                self.selected_image = item
                self.selected_video = None
                
            # Force a repaint
            self.update()

    def delete_image(self, image):
        self.uploaded_items.remove(image)
        if self.selected_image == image:
            self.selected_image = None
        self.update()

    def delete_video(self, video):
        video.worker.stop()
        video.thread.quit()
        video.thread.wait()
        video.timeline.setParent(None)
        video.timeline.deleteLater()
        self.uploaded_items.remove(video)
        self.update()

    def handle_right_click(self, event):
        pos = event.position()
        for item in reversed(self.uploaded_items):
            if ((isinstance(item, UploadedVideo) and self.is_over_video(pos, item)) or 
                (isinstance(item, UploadedImage) and self.is_over_image(pos, item))):
                self.show_item_context_menu(event.globalPosition().toPoint(), item)
                return

    def show_item_context_menu(self, global_pos, item):
        context_menu = QMenu(self)
        delete_action = context_menu.addAction(QIcon("icons/delete.png"), "Delete")
        bring_to_front_action = context_menu.addAction(QIcon("icons/bring_to_front.png"), "Bring to Front")
        
        if isinstance(item, UploadedVideo):
            play_pause_action = context_menu.addAction(QIcon("icons/play_pause.png"), "Play/Pause")
        
        action = context_menu.exec(global_pos)
        
        if action == delete_action:
            if isinstance(item, UploadedImage):
                self.delete_image(item)
            elif isinstance(item, UploadedVideo):
                self.delete_video(item)
        elif action == bring_to_front_action:
            self.bring_item_to_front(item)
        elif isinstance(item, UploadedVideo) and action == play_pause_action:
            item.play_pause()

    def is_over_any_video(self, pos):
        return any(self.is_over_video(pos, video) for video in self.uploaded_items if isinstance(video, UploadedVideo))

    def cleanup(self) -> None:
        """Ensure proper cleanup of all uploaded items and pixmaps."""
        try:
            # Clean up all uploaded items
            for item in self.uploaded_items[:]:
                if isinstance(item, UploadedVideo):
                    item.cleanup()
                elif isinstance(item, UploadedImage):
                    # If UploadedImage had resources to clean, handle them here
                    pass
                self.uploaded_items.remove(item)
            # Clear pixmaps
            self.pixmap = QPixmap(self.size())
            self.pixmap.fill(Qt.GlobalColor.white)
            self.drawing_layer = QPixmap(self.size())
            self.drawing_layer.fill(Qt.GlobalColor.transparent)
            
            self.update()
        except Exception as e:
            pass

    def draw_image(self, painter, image):
        """Draw image with selection border and resize handles"""
        target_rect = QRectF(
            image.position.x(),
            image.position.y(),
            image.size.width(),
            image.size.height()
        )
        
        painter.drawPixmap(target_rect.toRect(), image.pixmap)
        
        if image.selected:
            # Draw selection border
            pen = QPen(QColor(0, 120, 215), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(target_rect)
            
            # Draw resize handles
            handle_size = HANDLE_SIZE
            handle_color = QColor(0, 120, 215)
            painter.setBrush(handle_color)
            
            corners = [
                target_rect.topLeft(),
                target_rect.topRight(),
                target_rect.bottomLeft(),
                target_rect.bottomRight()
            ]
            
            for corner in corners:
                handle_rect = QRectF(
                    corner.x() - handle_size/2,
                    corner.y() - handle_size/2,
                    handle_size,
                    handle_size
                )
                painter.drawRect(handle_rect)

    def draw_video(self, painter, video):
        """Draw video with proper aspect ratio and selection handles"""
        try:
            target_rect = QRectF(
                video.position.x(),
                video.position.y(),
                video.size.width(),
                video.size.height()
            )
            
            if not video.current_pixmap.isNull():
                painter.drawPixmap(target_rect.toRect(), video.current_pixmap)
            
            if video.selected:
                # Draw selection border
                pen = QPen(QColor(0, 120, 215), 2, Qt.PenStyle.SolidLine)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(target_rect)
                
                # Draw resize handles
                handle_size = HANDLE_SIZE
                handle_color = QColor(0, 120, 215)
                painter.setBrush(handle_color)
                
                corners = [
                    target_rect.topLeft(),
                    target_rect.topRight(),
                    target_rect.bottomLeft(),
                    target_rect.bottomRight()
                ]
                
                for corner in corners:
                    handle_rect = QRectF(
                        corner.x() - handle_size/2,
                        corner.y() - handle_size/2,
                        handle_size,
                        handle_size
                    )
                    painter.drawRect(handle_rect)
        except Exception as e:
            pass

    def update_screen_share(self, pixmap):
        """Update the canvas with the captured screen pixmap while maintaining aspect ratio"""
        if pixmap.isNull():
            return
        
        # Create a new pixmap for the canvas
        canvas_pixmap = QPixmap(self.size())
        canvas_pixmap.fill(Qt.GlobalColor.black)
        
        # Calculate aspect ratios
        pixmap_aspect = pixmap.width() / pixmap.height()
        canvas_aspect = self.width() / self.height()
        
        # Use 100% of available space
        target_width = self.width()
        target_height = self.height()
        
        if pixmap_aspect > canvas_aspect:
            # Image is wider - fit to width
            scaled_width = int(target_width)
            scaled_height = int(target_width / pixmap_aspect)
        else:
            # Image is taller - fit to height
            scaled_height = int(target_height)
            scaled_width = int(target_height * pixmap_aspect)
        
        # Scale the pixmap with high quality
        scaled_pixmap = pixmap.scaled(
            scaled_width,
            scaled_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        # Calculate position to center the capture
        x = (self.width() - scaled_pixmap.width()) // 2
        y = (self.height() - scaled_pixmap.height()) // 2
        
        # Draw the captured content
        painter = QPainter(canvas_pixmap)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        # Draw the pixmap centered
        painter.drawPixmap(x, y, scaled_pixmap)
        painter.end()
        
        # Update the canvas pixmap
        self.pixmap = canvas_pixmap
        self.update()

    def clear_screen_share(self):
        """Clear the screen share content and restore default canvas"""
        print("Clearing screen share...")
        self.init_pixmaps()
        self.update()
        print("Screen share cleared")

    def init_pixmaps(self):
        """Initialize pixmaps with proper sizes"""
        self.pixmap = QPixmap(3000, 2000)
        self.pixmap.fill(Qt.GlobalColor.white)
        self.drawing_layer = QPixmap(3000, 2000)
        self.drawing_layer.fill(Qt.GlobalColor.transparent)

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.drawing_layer.copy())
            self.drawing_layer = self.undo_stack.pop()
            self.update()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.drawing_layer.copy())
            self.drawing_layer = self.redo_stack.pop()
            self.update()

class ToolButton(QPushButton):
    def __init__(self, icon_path, tooltip):
        super().__init__()
        icon = QIcon(icon_path)
        self.setIcon(icon)
        self.setIconSize(QSize(24, 24))
        self.setFixedSize(42, 42)
        self.setToolTip(tooltip)
        self.setCheckable(True)
        self.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.85);
                border: none;
                border-radius: 12px;
                padding: 8px;
                margin: 2px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.95);
            }
            QPushButton:checked {
                background-color: #007AFF;
            }
            QPushButton:checked:hover {
                background-color: #0066CC;
            }
            QPushButton:disabled {
                background-color: rgba(200, 200, 200, 0.7);
                opacity: 0.7;
            }
        """)
        
        # Add shadow effect
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(10)
        self.shadow.setColor(QColor(0, 0, 0, 40))
        self.shadow.setOffset(0, 2)
        self.setGraphicsEffect(self.shadow)

    # Remove animate_hover method as transitions are handled via stylesheets
    # Implement hover animations using event overrides
    def enterEvent(self, event):
        super().enterEvent(event)
        self.animate_hover(True)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.animate_hover(False)

    def animate_hover(self, hover):
        animation = QPropertyAnimation(self, b"geometry")
        animation.setDuration(200)
        if hover:
            # Slightly enlarge the button on hover
            animation.setEndValue(self.geometry().adjusted(-2, -2, 2, 2))
        else:
            # Return to original size when not hovered
            animation.setEndValue(self.geometry().adjusted(2, 2, -2, -2))
        animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        animation.start()

class ColorButton(QPushButton):
    def __init__(self, color):
        super().__init__()
        self.color = color
        self.setFixedSize(32, 32)  # Slightly smaller size
        self.setCheckable(True)
        
        # Add shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(8)
        shadow.setColor(QColor(0, 0, 0, 30))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)
        
        # Set circular shape with border
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.color.name()};
                border: 2px solid #888;
                border-radius: 16px;  /* Half of width/height */
            }}
            QPushButton:hover {{
                border: 2px solid #666;
            }}
            QPushButton:checked {{
                border: 3px solid #444;
            }}
        """)

    def set_button_color(self, selected_color):
        """Set button background color while maintaining circular shape"""
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {selected_color.name()};
                border: 2px solid #888;
                border-radius: 16px;
            }}
            QPushButton:hover {{
                border: 2px solid #666;
            }}
            QPushButton:checked {{
                border: 3px solid #444;
            }}
        """)

class SizeSlider(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Remove window flags and keep it as a regular widget
        self.setParent(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 4)
        
        # Create a container widget for the slider and label
        self.container = QWidget(self)
        self.container.setObjectName("container")
        container_layout = QHBoxLayout(self.container)
        container_layout.setContentsMargins(12, 6, 12, 6)
        container_layout.setSpacing(8)
        
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 50)
        self.slider.setValue(2)
        self.slider.setPageStep(1)
        self.slider.setTracking(True)
        container_layout.addWidget(self.slider)
        
        self.size_label = QLabel("2", self)
        self.size_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(self.size_label)
        
        self.layout.addWidget(self.container)
        self.setFixedSize(188, 48)
        
        # Update styles for a modern look without unsupported properties
        self.container.setStyleSheet("""
            QWidget#container {
                background-color: rgba(255, 255, 255, 0.9);
                border-radius: 12px;
                border: 1px solid rgba(0, 0, 0, 0.1);
            }
            QLabel {
                color: #2c3e50;
                font-weight: bold;
                font-size: 13px;
                min-width: 30px;
                padding: 4px 8px;
                background: rgba(255, 255, 255, 0.95);
                border-radius: 10px;
            }
            QSlider::groove:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #3498db, stop:1 #2980b9);
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #fff;
                border: 2px solid #2980b9;
                width: 16px;
                height: 16px;
                margin-top: -6px;
                margin-bottom: -6px;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: #ecf0f1;
                border: 2px solid #3498db;
            }
        """)
        
        # Add shadow effect to container without using box-shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 30))
        shadow.setOffset(0, 4)
        self.container.setGraphicsEffect(shadow)

    def showEvent(self, event):
        super().showEvent(event)
        if self.parentWidget():
            self.raise_()  # Ensure slider appears on top

    def hideEvent(self, event):
        super().hideEvent(event)

class WindowMenuItem(QWidget):
    def __init__(self, hwnd, title, parent=None):
        super().__init__(parent)
        self.hwnd = hwnd
        self.title = title

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(10)

        # Thumbnail Preview
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(100, 60)
        self.thumbnail_label.setScaledContents(True)
        thumbnail = self.capture_window_thumbnail(hwnd)
        if thumbnail:
            self.thumbnail_label.setPixmap(thumbnail)
        else:
            # Placeholder pixmap if thumbnail capture fails
            placeholder = QPixmap(100, 60)
            placeholder.fill(Qt.GlobalColor.gray)
            self.thumbnail_label.setPixmap(placeholder)
        self.layout.addWidget(self.thumbnail_label)

        # Window Title
        self.title_label = QLabel(title)
        self.title_label.setWordWrap(True)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.layout.addWidget(self.title_label)

    def capture_window_thumbnail(self, hwnd):
        try:
            # Ensure the window is not minimized
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.1)  # Brief pause to allow window to restore

            # Get window dimensions
            rect = win32gui.GetWindowRect(hwnd)
            x, y, right, bottom = rect
            width = right - x
            height = bottom - y

            if width == 0 or height == 0:
                raise Exception("Window has zero width or height.")

            # Initialize DC variables
            hwndDC = None
            mfcDC = None
            saveDC = None
            saveBitMap = None
            
            try:
                # Create device contexts and bitmap
                hwndDC = win32gui.GetWindowDC(hwnd)
                mfcDC = win32ui.CreateDCFromHandle(hwndDC)
                saveDC = mfcDC.CreateCompatibleDC()
                saveBitMap = win32ui.CreateBitmap()
                saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
                saveDC.SelectObject(saveBitMap)

                # Capture window content
                result = windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 3)
                if not result:
                    raise Exception("PrintWindow failed.")

                # Get bitmap info and bits
                bmpinfo = saveBitMap.GetInfo()
                bmpstr = saveBitMap.GetBitmapBits(True)

                # Create QImage and QPixmap
                qimage = QImage(bmpstr, bmpinfo['bmWidth'], bmpinfo['bmHeight'], QImage.Format.Format_ARGB32_Premultiplied)
                pixmap = QPixmap.fromImage(qimage)

                # Scale the pixmap
                pixmap = pixmap.scaled(
                    self.thumbnail_label.width(),
                    self.thumbnail_label.height(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                return pixmap

            finally:
                # Cleanup in reverse order of creation
                try:
                    if saveBitMap:
                        saveBitMap.GetHandle()  # Ensure handle exists before deletion
                        win32gui.DeleteObject(saveBitMap.GetHandle())
                    if saveDC:
                        saveDC.DeleteDC()
                    if mfcDC:
                        mfcDC.DeleteDC()
                    if hwndDC:
                        win32gui.ReleaseDC(hwnd, hwndDC)
                except Exception as cleanup_error:
                    print(f"Cleanup warning for window '{self.title}': {cleanup_error}")

        except Exception as e:
            print(f"Error capturing thumbnail for window '{self.title}': {e}")
            # Create a default thumbnail
            default_pixmap = QPixmap(self.thumbnail_label.width(), self.thumbnail_label.height())
            default_pixmap.fill(Qt.GlobalColor.gray)
            return default_pixmap

class PainterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Enhanced Modern Compact Painter")
        self.cleanup_done = False
        
        self.tools = [
            ("pen", "icons/pen.png", self.set_pen, "Pen"),
            ("eraser", "icons/eraser.png", self.set_eraser, "Eraser"),
            ("color_picker", "icons/color_picker.png", self.choose_color, "Color Picker"),
            ("undo", "icons/undo.png", self.undo, "Undo"),
            ("redo", "icons/redo.png", self.redo, "Redo"),
            ("clear", "icons/clear.png", self.clear_canvas, "Clear Canvas"),
            ("save", "icons/save.png", self.save_image, "Save"),
            ("upload_image", "icons/upload_image.png", self.upload_image, "Upload Image"),
            ("upload_video", "icons/upload_video.png", self.upload_video, "Upload Video"),
            ("camera", "icons/camera.png", self.toggle_camera, "Toggle Camera"),
            ("screen_share", "icons/screen_share.png", self.show_screen_share_menu, "Share Screen")
        ]
        
        self.init_ui()
        self.init_screen_sharing()
        self.camera = None
        self.camera_timer = QTimer(self)
        self.camera_timer.timeout.connect(self.update_camera_feed)
        self.camera_frame = None
        self.camera_lock = threading.Lock()
        
        # Add event filter to handle global clicks
        self.installEventFilter(self)
        
    def init_ui(self):
        self.canvas = Canvas()
        self.setCentralWidget(self.canvas)

        self.create_toolbar()
        self.create_size_slider()
        self.setMinimumSize(1024, 768)

    def start_camera(self):
        try:
            # Try different camera indices if 0 doesn't work
            for camera_index in range(3):  # Try indices 0, 1, 2
                self.camera = cv2.VideoCapture(camera_index)
                if self.camera.isOpened():
                    # Test reading a frame
                    ret, _ = self.camera.read()
                    if ret:
                        print(f"Successfully opened camera at index {camera_index}")
                        break
                    else:
                        self.camera.release()
                if camera_index == 2:  # If we've tried all indices
                    raise Exception("No working camera found")
            
            if not self.camera.isOpened():
                raise Exception("Failed to open camera")
            
            # Start the capture thread
            self.camera_thread = threading.Thread(target=self.camera_capture_thread, daemon=True)
            self.camera_thread.start()
            self.camera_timer.start(33)  # ~30 fps, more stable than 60fps
            
        except Exception as e:
            print(f"Camera error: {str(e)}")
            QMessageBox.warning(self, "Camera Error", str(e))
            self.tool_buttons["camera"].setChecked(False)
            self.stop_camera()

    def stop_camera(self):
        print("Stopping camera...")
        if self.camera:
            self.camera.release()
            self.camera = None
            self.camera_timer.stop()
            if hasattr(self, 'camera_thread'):
                self.camera_thread.join(timeout=1)
            self.camera_frame = None
            print("Camera stopped successfully")
        self.canvas.update()

    def closeEvent(self, event):
        if not self.cleanup_done:
            try:
                if hasattr(self, 'camera') and self.camera:
                    self.stop_camera()
                
                if hasattr(self, 'screen_capture_worker') and self.screen_capture_worker:
                    self.stop_screen_sharing()
                
                if hasattr(self, 'canvas'):
                    for item in self.canvas.uploaded_items:
                        if isinstance(item, UploadedVideo):
                            item.cleanup()
                    self.canvas.cleanup()
                
                if hasattr(self, 'camera_timer'):
                    self.camera_timer.stop()
                
                if hasattr(self, 'camera_thread'):
                    self.camera_thread.join(timeout=1)
                
                self.cleanup_done = True
                
            except Exception as e:
                print(f"Error during cleanup: {str(e)}")
            
        super().closeEvent(event)

    def create_toolbar(self):
        self.toolbar = QWidget(self)
        self.toolbar.setObjectName("toolbar")
        toolbar_layout = QHBoxLayout(self.toolbar)
        toolbar_layout.setContentsMargins(4, 4, 4, 4)  # Minimal margins
        toolbar_layout.setSpacing(4)  # Minimal spacing between elements

        # Left side tools container
        tools_container = QWidget()
        tools_container.setObjectName("toolsContainer")
        tools_layout = QHBoxLayout(tools_container)
        tools_layout.setContentsMargins(4, 4, 4, 4)  # Minimal margins
        tools_layout.setSpacing(2)  # Very tight spacing between buttons
        tools_container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        # Initialize buttons dictionary and exclusive button group
        self.tool_buttons = {}
        self.tool_button_group = QButtonGroup(self)  # {{ edit_1 }}
        self.tool_button_group.setExclusive(True)
        
        for tool_name, icon_path, action, tooltip in self.tools:
            button = ToolButton(icon_path, tooltip)
            button.clicked.connect(action)
            tools_layout.addWidget(button)
            self.tool_buttons[tool_name] = button
            self.tool_button_group.addButton(button)  # {{ edit_2 }}
        
        toolbar_layout.addWidget(tools_container)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setStyleSheet("""
            QFrame {
                background: rgba(0, 0, 0, 0.1);
                width: 1px;
                margin: 4px 4px;
            }
        """)
        toolbar_layout.addWidget(separator)

        # Colors container
        colors_container = QWidget()
        colors_container.setObjectName("colorsContainer")
        colors_layout = QHBoxLayout(colors_container)
        colors_layout.setContentsMargins(4, 4, 4, 4)  # Minimal margins
        colors_layout.setSpacing(2)  # Very tight spacing between color buttons
        colors_container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        # Add color buttons
        colors = [
            QColor(Qt.GlobalColor.black),
            QColor(Qt.GlobalColor.red),
            QColor(Qt.GlobalColor.blue),
            QColor(Qt.GlobalColor.green)
        ]

        self.color_buttons = []
        for color in colors:
            button = ColorButton(color)
            button.clicked.connect(lambda checked, c=color: self.set_color(c))
            colors_layout.addWidget(button)
            self.color_buttons.append(button)

        toolbar_layout.addWidget(colors_container)

        # Update toolbar height and styling
        self.toolbar.setFixedHeight(60)  # Slightly reduced height
        
        self.toolbar.setStyleSheet("""
            QWidget#toolbar {
                background-color: rgba(245, 245, 245, 0.98);
                border: 1px solid rgba(0, 0, 0, 0.1);
                border-radius: 16px;
            }
            QWidget#toolsContainer, QWidget#colorsContainer {
                background-color: rgba(255, 255, 255, 0.7);
                border-radius: 14px;
            }
        """)

        # Enhanced shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 40))
        shadow.setOffset(0, 5)
        self.toolbar.setGraphicsEffect(shadow)

        self.position_toolbar()

        # Set initial states
        self.tool_buttons["pen"].setChecked(True)
        self.color_buttons[0].setChecked(True)

    def position_toolbar(self):
        """Position and size the toolbar properly for any window size"""
        # Calculate minimum width needed for all buttons
        tools_width = len(self.tools) * 44  # 42px button + 2px margin
        colors_width = len(self.color_buttons) * 34  # 32px button + 2px margin
        separator_width = 10  # Separator width including margins
        min_width = tools_width + colors_width + separator_width + 20  # Add padding
        
        # Calculate toolbar width based on content
        window_width = self.width()
        toolbar_width = min(min_width + 40, window_width - 40)  # Add some padding, but don't exceed window width
        
        # Calculate x position to center the toolbar
        x = (window_width - toolbar_width) // 2
        
        # Calculate y position from bottom
        y = self.height() - self.toolbar.height() - 20
        
        # Ensure toolbar stays within window bounds
        x = max(10, min(x, window_width - toolbar_width - 10))
        y = max(10, min(y, self.height() - self.toolbar.height() - 10))
        
        # Update toolbar geometry
        self.toolbar.setGeometry(x, y, toolbar_width, self.toolbar.height())

    def resizeEvent(self, event):
        """Handle window resize events"""
        super().resizeEvent(event)
        self.position_toolbar()
        
        if self.size_slider.isVisible():
            self.position_size_slider()
        
        # Update screen capture worker's target size if active
        if hasattr(self, 'screen_capture_worker') and self.screen_capture_worker:
            self.screen_capture_worker.set_target_size(self.canvas.size())
        
        if hasattr(self, 'canvas'):
            new_pixmap = QPixmap(self.canvas.size())
            new_pixmap.fill(Qt.GlobalColor.white)
            painter = QPainter(new_pixmap)
            painter.drawPixmap(0, 0, self.canvas.pixmap)
            self.canvas.pixmap = new_pixmap
            
            new_drawing_layer = QPixmap(self.canvas.size())
            new_drawing_layer.fill(Qt.GlobalColor.transparent)
            painter = QPainter(new_drawing_layer)
            painter.drawPixmap(0, 0, self.canvas.drawing_layer)
            self.canvas.drawing_layer = new_drawing_layer

    def create_size_slider(self):
        self.size_slider = SizeSlider(self)
        self.size_slider.slider.valueChanged.connect(self.set_brush_size)
        self.size_slider.hide()

    def set_pen(self):
        self.set_tool("pen")
        # Ensure color picker and eraser are unchecked
        if self.tool_buttons["color_picker"].isChecked():
            self.tool_buttons["color_picker"].setChecked(False)
        if self.tool_buttons["eraser"].isChecked():
            self.tool_buttons["eraser"].setChecked(False)

    def set_eraser(self):
        self.set_tool("eraser")
        # Ensure color picker and pen are unchecked
        if self.tool_buttons["color_picker"].isChecked():
            self.tool_buttons["color_picker"].setChecked(False)
        if self.tool_buttons["pen"].isChecked():
            self.tool_buttons["pen"].setChecked(False)

    def set_tool(self, tool):
        # Uncheck all tools first
        for button in self.tool_buttons.values():
            button.setChecked(False)
            
        # Set the new tool
        self.canvas.tool = tool
        self.tool_buttons[tool].setChecked(True)
        self.animate_button(self.tool_buttons[tool])

        # Handle size slider visibility
        if tool in ["pen", "eraser"]:
            self.position_size_slider()
            self.size_slider.show()
            self.canvas.setCursor(Qt.CursorShape.BlankCursor)
        else:
            self.size_slider.hide()
            self.canvas.setCursor(Qt.CursorShape.ArrowCursor)

        self.canvas.update()

    def position_size_slider(self):
        """Position and size the size slider properly for any window size"""
        tool = "pen" if self.canvas.tool == "pen" else "eraser"
        button = self.tool_buttons[tool]
        button_pos = button.mapTo(self, button.rect().center())
        
        x = button_pos.x() - self.size_slider.width() // 2
        y = button_pos.y() - self.size_slider.height() - 15  # {{ edit_1 }} Increased vertical offset from 5 to 15
        
        # Ensure the slider stays within the window bounds
        x = max(10, min(x, self.width() - self.size_slider.width() - 10))
        y = max(10, min(y, self.height() - self.size_slider.height() - 10))
        
        # Update slider geometry
        self.size_slider.move(x, y)
        self.size_slider.raise_()  # Ensure it's on top

    def choose_color(self):
        # Switch to pen tool when color picker is used
        self.set_tool("pen")
        color = QColorDialog.getColor(self.canvas.color, self, "Choose Color", 
                                    QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            self.set_color(color)

    def set_color(self, color):
        self.canvas.set_color(color)
        self.update_color_buttons(color)

    def update_color_buttons(self, selected_color):
        for button in self.color_buttons:
            button.setChecked(button.color.rgb() == selected_color.rgb())
            if button.color.rgb() == selected_color.rgb():
                self.animate_button(button)
                # Add a border effect for selected button
                button.setStyleSheet(button.styleSheet() + """
                    QPushButton {
                        border: 2px solid #3498DB;
                    }
                """)
            else:
                # Reset to default style
                button.set_button_color(button.color)

    def set_brush_size(self, size):
        self.canvas.brush_size = size
        self.size_slider.size_label.setText(str(size))
        self.canvas.update()

    def undo(self):
        if self.canvas.undo_stack:
            self.canvas.redo_stack.append(self.canvas.drawing_layer.copy())
            self.canvas.drawing_layer = self.canvas.undo_stack.pop()
            self.canvas.update()

    def redo(self):
        if self.canvas.redo_stack:
            self.canvas.undo_stack.append(self.canvas.drawing_layer.copy())
            self.canvas.drawing_layer = self.canvas.redo_stack.pop()
            self.canvas.update()

    def clear_canvas(self):
        self.canvas.undo_stack.append(self.canvas.drawing_layer.copy())
        self.canvas.clear()

    def save_image(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Image", "", "PNG Files (*.png);;JPEG Files (*.jpg *.jpeg)")
        if file_path:
            combined_pixmap = QPixmap(self.canvas.size())
            combined_pixmap.fill(Qt.GlobalColor.white)
            painter = QPainter(combined_pixmap)
            painter.drawPixmap(0, 0, self.canvas.pixmap)
            painter.drawPixmap(0, 0, self.canvas.drawing_layer)
            painter.end()
            combined_pixmap.save(file_path)

    def animate_button(self, button):
        animation = QPropertyAnimation(button, b"geometry")
        animation.setDuration(150)
        animation.setStartValue(button.geometry())
        animation.setEndValue(button.geometry().adjusted(-3, -3, 3, 3))
        animation.setLoopCount(2)
        animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        animation.start()

    def upload_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Upload Image", "", "Image Files (*.png *.jpg *.jpeg *.bmp)")
        if file_path:
            self.canvas.add_uploaded_image(file_path)

    def upload_video(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Upload Video", "", "Video Files (*.mp4 *.avi *.mov *.wmv)")
        if file_path:
            print(f"Uploading video: {file_path}")
            self.canvas.add_uploaded_video(file_path)

    def toggle_camera(self):
        if self.camera is None:
            try:
                self.start_camera()
                self.tool_buttons["camera"].setChecked(True)
            except Exception as e:
                print(f"Error starting camera: {e}")
                self.tool_buttons["camera"].setChecked(False)
                QMessageBox.warning(self, "Camera Error", str(e))
        else:
            try:
                self.switch_to_canvas()
                self.tool_buttons["camera"].setChecked(False)
            except Exception as e:
                print(f"Error stopping camera: {e}")

    def switch_to_canvas(self):
        self.stop_camera()
        self.restore_default_canvas()

    def restore_default_canvas(self):
        self.canvas.pixmap = QPixmap(self.canvas.size())
        self.canvas.pixmap.fill(Qt.GlobalColor.white)
        self.canvas.drawing_layer.fill(Qt.GlobalColor.transparent)
        self.canvas.update()

    def camera_capture_thread(self):
        print("Camera capture thread started")
        while self.camera and self.camera.isOpened():
            try:
                ret, frame = self.camera.read()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    with self.camera_lock:
                        self.camera_frame = frame
                else:
                    print("Failed to read frame")
                    break
                time.sleep(0.01)  # Small delay to prevent thread from consuming too much CPU
            except Exception as e:
                print(f"Error in camera thread: {str(e)}")
                break
        print("Camera capture thread ended")

    def update_camera_feed(self, frame=None):
        try:
            if frame is None and self.camera:
                with self.camera_lock:
                    if self.camera_frame is None:
                        return
                    frame = self.camera_frame.copy()
            elif frame is None:
                return

            h, w, ch = frame.shape
            bytes_per_line = ch * w
            qt_image = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            if qt_image.isNull():
                print("Failed to create QImage from camera frame")
                return
            
            camera_pixmap = QPixmap.fromImage(qt_image)
            if camera_pixmap.isNull():
                print("Failed to create QPixmap from QImage")
                return
            
            # Calculate scaling to fit the canvas
            canvas_ratio = self.canvas.width() / self.canvas.height()
            image_ratio = w / h
            
            if canvas_ratio > image_ratio:
                scaled_height = self.canvas.height()
                scaled_width = int(scaled_height * image_ratio)
            else:
                scaled_width = self.canvas.width()
                scaled_height = int(scaled_width / image_ratio)
            
            scaled_pixmap = camera_pixmap.scaled(
                scaled_width, 
                scaled_height, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            
            # Create canvas pixmap and center the camera feed
            self.canvas.pixmap = QPixmap(self.canvas.size())
            self.canvas.pixmap.fill(Qt.GlobalColor.black)
            
            x = (self.canvas.width() - scaled_width) // 2
            y = (self.canvas.height() - scaled_height) // 2
            
            painter = QPainter(self.canvas.pixmap)
            painter.drawPixmap(x, y, scaled_pixmap)
            painter.end()
            
            self.canvas.update()
            
        except Exception as e:
            print(f"Error updating camera feed: {str(e)}")

    def eventFilter(self, obj, event):
        if event.type() == event.Type.MouseButtonPress:
            if self.size_slider.isVisible():
                # Get global click position
                global_pos = event.globalPosition().toPoint()
                # Convert slider geometry to global coordinates
                slider_geo = QRect(
                    self.size_slider.mapToGlobal(self.size_slider.rect().topLeft()),
                    self.size_slider.size()
                )
                # Hide slider if click is outside
                if not slider_geo.contains(global_pos):
                    self.size_slider.hide()
        return super().eventFilter(obj, event)

    def init_screen_sharing(self):
        # Initialize screen capture worker
        self.screen_capture_worker = None
        self.screen_capture_thread = None
        
    def start_screen_sharing(self, monitor=None, window_id=None):
        try:
            # Stop existing capture if running
            if self.screen_capture_worker:
                self.stop_screen_sharing()
            
            # Create new worker
            self.screen_capture_worker = ScreenCaptureWorker(monitor, window_id)
            self.screen_capture_thread = QThread()
            self.screen_capture_worker.moveToThread(self.screen_capture_thread)
            
            # Set target size based on canvas size
            self.screen_capture_worker.set_target_size(self.canvas.size())
            
            # Connect signals
            self.screen_capture_worker.frame_ready.connect(self.canvas.update_screen_share)
            self.screen_capture_worker.error_occurred.connect(self.handle_screen_capture_error)
            self.screen_capture_thread.started.connect(self.screen_capture_worker.capture_screen)
            
            # Start capture
            self.screen_capture_thread.start()
            self.screen_capture_worker.start_capture()
            
            # Update UI
            self.tool_buttons["screen_share"].setChecked(True)
            
        except Exception as e:
            QMessageBox.critical(self, "Screen Sharing Error", f"Failed to start screen sharing: {str(e)}")
            self.stop_screen_sharing()

    def handle_screen_capture_error(self, error_message):
        print(f"Screen capture error: {error_message}")
        if "Window no longer exists" in error_message:
            self.stop_screen_sharing()
            QMessageBox.warning(self, "Screen Sharing Error", 
                              "The selected window is no longer available. Screen sharing has been stopped.")

    def stop_screen_sharing(self):
        """Stop screen sharing with improved cleanup"""
        print("Stopping screen sharing...")
        try:
            if self.screen_capture_worker:
                # Stop capturing first
                self.screen_capture_worker.stop_capture()
                self.screen_capture_worker.stop()
                
                # Disconnect signals safely
                try:
                    if hasattr(self.screen_capture_worker, 'frame_ready'):
                        try:
                            self.screen_capture_worker.frame_ready.disconnect()
                        except TypeError:
                            pass  # Signal was not connected
                    if hasattr(self.screen_capture_worker, 'error_occurred'):
                        try:
                            self.screen_capture_worker.error_occurred.disconnect()
                        except TypeError:
                            pass  # Signal was not connected
                except Exception as e:
                    print(f"Error disconnecting signals: {e}")
                
                # Stop thread with timeout
                if self.screen_capture_thread:
                    print("Stopping capture thread...")
                    self.screen_capture_thread.quit()
                    if not self.screen_capture_thread.wait(2000):  # Wait up to 2 seconds
                        print("Thread did not quit normally, forcing termination...")
                        self.screen_capture_thread.terminate()
                        self.screen_capture_thread.wait()
                
                # Clear references
                self.screen_capture_worker = None
                self.screen_capture_thread = None
                
                # Update UI
                self.tool_buttons["screen_share"].setChecked(False)
                
                # Clear canvas
                print("Restoring canvas...")
                self.canvas.clear_screen_share()
                
                print("Screen sharing stopped successfully")
                
        except Exception as e:
            print(f"Error stopping screen sharing: {str(e)}")
            # Ensure UI is updated even if error occurs
            self.tool_buttons["screen_share"].setChecked(False)
            raise

    def show_screen_share_menu(self):
        # If already sharing, just show the dialog
        dialog = ScreenShareDialog(self)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        
        # Update button state
        if self.screen_capture_worker and self.screen_capture_worker.capturing:
            self.tool_buttons["screen_share"].setChecked(True)
        else:
            self.tool_buttons["screen_share"].setChecked(False)
        
        dialog.exec()

# Add the ScreenShareDialog class
class ScreenShareDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Screen Share")
        self.setFixedSize(600, 500)
        
        layout = QVBoxLayout(self)
        
        # Add buttons container at the top
        buttons_container = QWidget()
        buttons_layout = QHBoxLayout(buttons_container)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        
        # Add stop button
        self.stop_button = QPushButton("Stop Sharing", self)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:pressed {
                background-color: #bd2130;
            }
            QPushButton:disabled {
                background-color: #6c757d;
                opacity: 0.65;
            }
        """)
        self.stop_button.clicked.connect(self.stop_sharing)
        buttons_layout.addWidget(self.stop_button)
        
        # Add spacer to push stop button to the right
        buttons_layout.addStretch()
        
        # Add buttons container to main layout
        layout.addWidget(buttons_container)
        
        label = QLabel("Select Screen or Window to Share", self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        
        # Tabs for Screen, Window, and Browser Tab selection
        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs)
        
        # Screen Selection Tab
        self.screen_tab = QWidget()
        self.tabs.addTab(self.screen_tab, "Select Screen")
        self.init_screen_tab()
        
        # Window Selection Tab
        self.window_tab = QWidget()
        self.tabs.addTab(self.window_tab, "Select Window")
        self.init_window_tab()

        # Cancel Button
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
            QPushButton:pressed {
                background-color: #545b62;
            }
        """)
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(self.cancel_button)
        
        # Update stop button state based on current sharing status
        self.update_stop_button_state()
    
    def init_screen_tab(self):
        layout = QVBoxLayout(self.screen_tab)
        
        self.screen_list = QListWidget(self.screen_tab)
        layout.addWidget(self.screen_list)
        
        # Populate screen list
        monitors = mss.mss().monitors[1:]  # Exclude the virtual monitor at index 0
        for idx, monitor in enumerate(monitors, start=1):
            self.screen_list.addItem(f"Screen {idx}: {monitor['width']}x{monitor['height']} at ({monitor['left']}, {monitor['top']}")
        
        select_button = QPushButton("Share Selected Screen", self.screen_tab)
        select_button.clicked.connect(self.share_selected_screen)
        layout.addWidget(select_button)
    
    def init_window_tab(self):
        layout = QVBoxLayout(self.window_tab)
        
        self.window_list = QListWidget(self.window_tab)
        layout.addWidget(self.window_list)
        
        # Populate window list
        self.populate_window_list()
        
        select_button = QPushButton("Share Selected Window", self.window_tab)
        select_button.clicked.connect(self.share_selected_window)
        layout.addWidget(select_button)
    
    def populate_window_list(self):
        selector = WindowSelector()
        windows = selector.get_window_list()
        for hwnd, title, class_name in windows:
            self.window_list.addItem(f"{title} (Class: {class_name})")
        if not windows:
            self.window_list.addItem("No suitable windows found.")
    
    def share_selected_screen(self):
        selected_items = self.screen_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Selection Error", "Please select a screen to share.")
            return
        selected_index = self.screen_list.row(selected_items[0]) + 1  # Monitor index starts at 1
        with mss.mss() as sct:
            monitor = sct.monitors[selected_index]
            self.parent().start_screen_sharing(monitor=monitor)
        self.accept()
    
    def share_selected_window(self):
        selected_items = self.window_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Selection Error", "Please select a window to share.")
            return
        selected_text = selected_items[0].text()
        hwnd = self.extract_hwnd_from_text(selected_text)
        if hwnd:
            self.parent().start_screen_sharing(window_id=hwnd)
            self.accept()
        else:
            QMessageBox.warning(self, "Selection Error", "Invalid window selected.")

    def extract_hwnd_from_text(self, text):
        """Extract hwnd from window list item text."""
        try:
            # Assuming the format "Window Title (Class: ClassName)" or "Tab Title (Class: ClassName)"
            title, _ = text.split(" (Class:")
            selector = WindowSelector()
            # First, attempt to find in browser windows
            browser_windows = selector.get_browser_windows()
            for hwnd, win_title, _ in browser_windows:
                if win_title == title.strip():
                    return hwnd
            # If not found in browser windows, search in all windows
            windows = selector.get_window_list()
            for hwnd, win_title, _ in windows:
                if win_title == title.strip():
                    return hwnd
            return None
        except Exception as e:
            print(f"Error extracting hwnd: {e}")
            return None

    def update_stop_button_state(self):
        """Update stop button enabled state based on whether sharing is active"""
        if self.parent():
            is_sharing = (hasattr(self.parent(), 'screen_capture_worker') and 
                         self.parent().screen_capture_worker is not None and 
                         self.parent().screen_capture_worker.capturing)
            self.stop_button.setEnabled(is_sharing)
            # Update button text based on state
            self.stop_button.setText("Stop Sharing" if is_sharing else "Not Sharing")

    def stop_sharing(self):
        """Stop screen sharing and update UI"""
        if self.parent():
            try:
                print("Initiating screen share stop from dialog...")
                self.parent().stop_screen_sharing()
                self.update_stop_button_state()
                QMessageBox.information(self, "Screen Sharing", "Screen sharing has been stopped.")
                # Optionally close the dialog after stopping
                self.accept()
            except Exception as e:
                print(f"Error in stop_sharing: {str(e)}")
                QMessageBox.warning(self, "Error", f"Failed to stop screen sharing: {str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = PainterApp()
    window.show()
    sys.exit(app.exec())