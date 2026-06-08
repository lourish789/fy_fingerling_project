"""
Video Processor for Fingerling Counting

Handles video input from files, webcams, streams, URLs, and images,
and processes frames through the detection pipeline.
"""

import cv2
import numpy as np
import time
import threading
import re
import os
import tempfile
from queue import Queue
from typing import Optional, Callable, Generator, Tuple, Dict, Any, List, Union
from pathlib import Path
from dataclasses import dataclass
from urllib.parse import urlparse
import requests


@dataclass
class FrameData:
    """Container for frame and metadata."""
    frame: np.ndarray
    frame_number: int
    timestamp: float
    fps: float
    source_type: str = "video"  # "video", "image", "camera", "stream"


class URLVideoHandler:
    """
    Handles video URLs including YouTube, direct video links, etc.
    """
    
    @staticmethod
    def is_url(source: str) -> bool:
        """Check if source is a URL."""
        if not isinstance(source, str):
            return False
        try:
            result = urlparse(source)
            return result.scheme in ('http', 'https', 'rtsp', 'rtmp')
        except:
            return False
    
    @staticmethod
    def is_youtube_url(url: str) -> bool:
        """Check if URL is a YouTube video."""
        youtube_patterns = [
            r'(youtube\.com/watch\?v=)',
            r'(youtu\.be/)',
            r'(youtube\.com/embed/)',
            r'(youtube\.com/v/)'
        ]
        return any(re.search(pattern, url) for pattern in youtube_patterns)
    
    @staticmethod
    def get_youtube_stream_url(url: str) -> Optional[str]:
        """Get direct stream URL from YouTube using yt-dlp."""
        try:
            import yt_dlp
            
            ydl_opts = {
                'format': 'best[ext=mp4]/best',
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info.get('url')
        except ImportError:
            print("Warning: yt-dlp not installed. Install with: pip install yt-dlp")
            return None
        except Exception as e:
            print(f"Error extracting YouTube URL: {e}")
            return None
    
    @staticmethod
    def download_video(url: str, output_path: Optional[str] = None) -> Optional[str]:
        """Download video from URL to local file."""
        try:
            if output_path is None:
                fd, output_path = tempfile.mkstemp(suffix='.mp4')
                os.close(fd)
            
            # Check if it's a YouTube URL
            if URLVideoHandler.is_youtube_url(url):
                try:
                    import yt_dlp
                    ydl_opts = {
                        'format': 'best[ext=mp4]/best',
                        'outtmpl': output_path.replace('.mp4', '') + '.%(ext)s',
                        'quiet': True,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                    # Find the downloaded file
                    base = output_path.replace('.mp4', '')
                    for ext in ['.mp4', '.webm', '.mkv']:
                        if os.path.exists(base + ext):
                            return base + ext
                    return output_path
                except ImportError:
                    print("yt-dlp not installed for YouTube downloads")
                    return None
            else:
                # Direct download for regular URLs
                response = requests.get(url, stream=True, timeout=30)
                response.raise_for_status()
                
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                return output_path
                
        except Exception as e:
            print(f"Error downloading video: {e}")
            return None


class ImageProcessor:
    """
    Handles single images and image batches for fingerling detection.
    """
    
    SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}
    
    @staticmethod
    def is_image_file(path: str) -> bool:
        """Check if path is an image file."""
        if not isinstance(path, str):
            return False
        return Path(path).suffix.lower() in ImageProcessor.SUPPORTED_FORMATS
    
    @staticmethod
    def is_image_url(url: str) -> bool:
        """Check if URL points to an image."""
        if not URLVideoHandler.is_url(url):
            return False
        parsed = urlparse(url)
        path = parsed.path.lower()
        return any(path.endswith(ext) for ext in ImageProcessor.SUPPORTED_FORMATS)
    
    @staticmethod
    def load_image(source: str) -> Optional[np.ndarray]:
        """Load image from file path or URL."""
        try:
            if URLVideoHandler.is_url(source):
                # Download image from URL
                response = requests.get(source, timeout=30)
                response.raise_for_status()
                img_array = np.frombuffer(response.content, np.uint8)
                image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            else:
                # Load from file
                image = cv2.imread(source)
            
            return image
        except Exception as e:
            print(f"Error loading image: {e}")
            return None
    
    @staticmethod
    def load_images_from_directory(directory: str) -> List[Tuple[str, np.ndarray]]:
        """Load all images from a directory."""
        images = []
        directory = Path(directory)
        
        if not directory.is_dir():
            return images
        
        for file_path in sorted(directory.iterdir()):
            if file_path.suffix.lower() in ImageProcessor.SUPPORTED_FORMATS:
                image = cv2.imread(str(file_path))
                if image is not None:
                    images.append((str(file_path), image))
        
        return images


class VideoProcessor:
    """
    Video processing pipeline for fingerling counting.
    
    Supports:
    - Video files (MP4, AVI, etc.)
    - Webcam/USB cameras
    - RTSP/RTMP streams
    - YouTube and web video URLs
    - Image sequences
    - Single images
    - Image directories
    """
    
    def __init__(
        self,
        source: Union[str, int] = 0,
        target_fps: Optional[float] = None,
        frame_width: Optional[int] = None,
        frame_height: Optional[int] = None,
        buffer_size: int = 10,
        auto_reconnect: bool = True,
        reconnect_delay: float = 5.0
    ):
        """
        Initialize video processor.
        
        Args:
            source: Video source (file path, camera index, URL, or image path).
            target_fps: Target FPS for processing (None = original FPS).
            frame_width: Target frame width (None = original).
            frame_height: Target frame height (None = original).
            buffer_size: Frame buffer size for async processing.
            auto_reconnect: Auto-reconnect on stream failure.
            reconnect_delay: Delay between reconnection attempts.
        """
        self.original_source = source
        self.source = source
        self.target_fps = target_fps
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.buffer_size = buffer_size
        self.auto_reconnect = auto_reconnect
        self.reconnect_delay = reconnect_delay
        
        self.cap: Optional[cv2.VideoCapture] = None
        self.is_running = False
        self.frame_count = 0
        self.start_time = 0.0
        
        # Source type detection
        self.source_type = self._detect_source_type(source)
        self.is_live = self.source_type in ('camera', 'stream', 'youtube_live')
        
        # For image processing
        self.image_list: List[Tuple[str, np.ndarray]] = []
        self.image_index = 0
        
        # Async processing
        self.frame_queue: Queue = Queue(maxsize=buffer_size)
        self.read_thread: Optional[threading.Thread] = None
        
        # Video properties
        self.original_fps = 30.0
        self.original_width = 1280
        self.original_height = 720
        self.total_frames = 0
        
        # Temporary file for downloaded videos
        self._temp_file: Optional[str] = None
    
    def _detect_source_type(self, source: Union[str, int]) -> str:
        """Detect the type of video source."""
        if isinstance(source, int):
            return 'camera'
        
        source_str = str(source)
        
        # Check for URLs
        if URLVideoHandler.is_url(source_str):
            if URLVideoHandler.is_youtube_url(source_str):
                return 'youtube'
            if source_str.startswith('rtsp://') or source_str.startswith('rtmp://'):
                return 'stream'
            if ImageProcessor.is_image_url(source_str):
                return 'image_url'
            return 'video_url'
        
        # Check for local files
        path = Path(source_str)
        if path.is_dir():
            return 'image_directory'
        if path.exists():
            if ImageProcessor.is_image_file(source_str):
                return 'image'
            return 'video'
        
        # Could be a camera index as string
        try:
            int(source_str)
            return 'camera'
        except ValueError:
            pass
        
        return 'unknown'
    
    def open(self) -> bool:
        """
        Open the video source.
        
        Returns:
            True if successful, False otherwise.
        """
        try:
            print(f"Opening source: {self.original_source} (type: {self.source_type})")
            
            # Handle different source types
            if self.source_type == 'image':
                return self._open_image(str(self.source))
            
            elif self.source_type == 'image_url':
                return self._open_image_url(str(self.source))
            
            elif self.source_type == 'image_directory':
                return self._open_image_directory(str(self.source))
            
            elif self.source_type == 'youtube':
                return self._open_youtube(str(self.source))
            
            elif self.source_type == 'video_url':
                return self._open_video_url(str(self.source))
            
            elif self.source_type == 'stream':
                return self._open_stream(str(self.source))
            
            elif self.source_type == 'camera':
                return self._open_camera(self.source)
            
            else:
                return self._open_video_file(str(self.source))
            
        except Exception as e:
            print(f"Error opening video: {e}")
            return False
    
    def _open_camera(self, source: Union[str, int]) -> bool:
        """Open camera source."""
        camera_index = int(source) if isinstance(source, str) else source
        
        # Try different backends for better compatibility
        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
        
        for backend in backends:
            self.cap = cv2.VideoCapture(camera_index, backend)
            if self.cap.isOpened():
                break
        
        if not self.cap or not self.cap.isOpened():
            print(f"Failed to open camera: {camera_index}")
            return False
        
        # Set camera properties for better performance
        if self.frame_width:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
        if self.frame_height:
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
        
        # Set buffer size to reduce latency
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        return self._finalize_open()
    
    def _open_video_file(self, path: str) -> bool:
        """Open local video file."""
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            print(f"Failed to open video file: {path}")
            return False
        return self._finalize_open()
    
    def _open_stream(self, url: str) -> bool:
        """Open RTSP/RTMP stream."""
        # Use TCP for more reliable streaming
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
        
        self.cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        if not self.cap.isOpened():
            print(f"Failed to open stream: {url}")
            return False
        
        # Reduce buffer for lower latency
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        return self._finalize_open()
    
    def _open_youtube(self, url: str) -> bool:
        """Open YouTube video."""
        print("Extracting YouTube video URL...")
        
        stream_url = URLVideoHandler.get_youtube_stream_url(url)
        if stream_url:
            self.cap = cv2.VideoCapture(stream_url)
            if self.cap.isOpened():
                return self._finalize_open()
        
        # Fallback: download video
        print("Downloading YouTube video...")
        downloaded_path = URLVideoHandler.download_video(url)
        if downloaded_path:
            self._temp_file = downloaded_path
            self.cap = cv2.VideoCapture(downloaded_path)
            if self.cap.isOpened():
                return self._finalize_open()
        
        print("Failed to open YouTube video")
        return False
    
    def _open_video_url(self, url: str) -> bool:
        """Open video from direct URL."""
        # Try direct streaming first
        self.cap = cv2.VideoCapture(url)
        if self.cap.isOpened():
            return self._finalize_open()
        
        # Download if direct streaming fails
        print("Downloading video from URL...")
        downloaded_path = URLVideoHandler.download_video(url)
        if downloaded_path:
            self._temp_file = downloaded_path
            self.cap = cv2.VideoCapture(downloaded_path)
            if self.cap.isOpened():
                return self._finalize_open()
        
        print(f"Failed to open video URL: {url}")
        return False
    
    def _open_image(self, path: str) -> bool:
        """Open single image file."""
        image = ImageProcessor.load_image(path)
        if image is None:
            print(f"Failed to load image: {path}")
            return False
        
        self.image_list = [(path, image)]
        self.image_index = 0
        self.original_width = image.shape[1]
        self.original_height = image.shape[0]
        self.original_fps = 1.0
        self.total_frames = 1
        self.is_running = True
        self.start_time = time.time()
        
        print(f"Image loaded: {self.original_width}x{self.original_height}")
        return True
    
    def _open_image_url(self, url: str) -> bool:
        """Open image from URL."""
        image = ImageProcessor.load_image(url)
        if image is None:
            print(f"Failed to load image from URL: {url}")
            return False
        
        self.image_list = [(url, image)]
        self.image_index = 0
        self.original_width = image.shape[1]
        self.original_height = image.shape[0]
        self.original_fps = 1.0
        self.total_frames = 1
        self.is_running = True
        self.start_time = time.time()
        
        print(f"Image loaded from URL: {self.original_width}x{self.original_height}")
        return True
    
    def _open_image_directory(self, directory: str) -> bool:
        """Open directory of images."""
        self.image_list = ImageProcessor.load_images_from_directory(directory)
        
        if not self.image_list:
            print(f"No images found in directory: {directory}")
            return False
        
        self.image_index = 0
        first_image = self.image_list[0][1]
        self.original_width = first_image.shape[1]
        self.original_height = first_image.shape[0]
        self.original_fps = 1.0
        self.total_frames = len(self.image_list)
        self.is_running = True
        self.start_time = time.time()
        
        print(f"Loaded {len(self.image_list)} images from directory")
        return True
    
    def _finalize_open(self) -> bool:
        """Finalize video capture opening."""
        if self.cap is None or not self.cap.isOpened():
            return False
        
        # Get original properties
        self.original_fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.original_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.original_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # For live sources, total_frames is 0 or negative
        if self.total_frames <= 0:
            self.total_frames = 0
            self.is_live = True
        
        self.is_running = True
        self.start_time = time.time()
        
        print(f"Video opened: {self.original_width}x{self.original_height} @ {self.original_fps:.1f} FPS")
        if self.is_live:
            print("Live source detected - continuous streaming mode")
        
        return True
    
    def read(self) -> Optional[FrameData]:
        """
        Read a single frame.
        
        Returns:
            FrameData if successful, None if end of video or error.
        """
        # Handle image sources
        if self.source_type in ('image', 'image_url', 'image_directory'):
            return self._read_image()
        
        # Handle video sources
        if self.cap is None or not self.is_running:
            return None
        
        ret, frame = self.cap.read()
        
        if not ret:
            # For live sources, attempt reconnection
            if self.is_live and self.auto_reconnect:
                return self._handle_reconnect()
            return None
        
        self.frame_count += 1
        timestamp = time.time() - self.start_time
        
        # Resize if needed
        if self.frame_width and self.frame_height:
            if frame.shape[1] != self.frame_width or frame.shape[0] != self.frame_height:
                frame = cv2.resize(frame, (self.frame_width, self.frame_height))
        
        # Calculate actual FPS
        actual_fps = self.frame_count / max(timestamp, 0.001)
        
        return FrameData(
            frame=frame,
            frame_number=self.frame_count,
            timestamp=timestamp,
            fps=actual_fps,
            source_type=self.source_type
        )
    
    def _read_image(self) -> Optional[FrameData]:
        """Read from image source."""
        if self.image_index >= len(self.image_list):
            return None
        
        path, image = self.image_list[self.image_index]
        self.image_index += 1
        self.frame_count += 1
        
        # Resize if needed
        if self.frame_width and self.frame_height:
            if image.shape[1] != self.frame_width or image.shape[0] != self.frame_height:
                image = cv2.resize(image, (self.frame_width, self.frame_height))
        
        return FrameData(
            frame=image.copy(),
            frame_number=self.frame_count,
            timestamp=time.time() - self.start_time,
            fps=1.0,
            source_type=self.source_type
        )
    
    def _handle_reconnect(self) -> Optional[FrameData]:
        """Handle reconnection for live sources."""
        print(f"\nConnection lost. Attempting reconnect in {self.reconnect_delay}s...")
        
        if self.cap:
            self.cap.release()
        
        time.sleep(self.reconnect_delay)
        
        # Attempt to reopen
        if self.open():
            return self.read()
        
        return None
    
    def frames(self) -> Generator[FrameData, None, None]:
        """
        Generator that yields frames.
        
        Yields:
            FrameData for each frame.
        """
        if not self.is_running:
            if not self.open():
                return
        
        frame_interval = 1.0 / self.target_fps if self.target_fps else 0
        last_frame_time = 0.0
        
        while self.is_running:
            current_time = time.time()
            
            # Frame rate limiting
            if self.target_fps and (current_time - last_frame_time) < frame_interval:
                time.sleep(0.001)
                continue
            
            frame_data = self.read()
            
            if frame_data is None:
                break
            
            last_frame_time = current_time
            yield frame_data
    
    def start_async(self) -> None:
        """Start asynchronous frame reading in background thread."""
        if self.read_thread is not None:
            return
        
        if not self.is_running:
            if not self.open():
                return
        
        self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.read_thread.start()
    
    def _read_loop(self) -> None:
        """Background thread for reading frames."""
        while self.is_running:
            if self.frame_queue.full():
                time.sleep(0.001)
                continue
            
            frame_data = self.read()
            
            if frame_data is None:
                self.is_running = False
                break
            
            try:
                self.frame_queue.put_nowait(frame_data)
            except:
                pass
    
    def get_frame_async(self, timeout: float = 1.0) -> Optional[FrameData]:
        """
        Get frame from async buffer.
        
        Args:
            timeout: Maximum time to wait for frame.
            
        Returns:
            FrameData if available, None otherwise.
        """
        try:
            return self.frame_queue.get(timeout=timeout)
        except:
            return None
    
    def close(self) -> None:
        """Close video source and cleanup."""
        self.is_running = False
        
        if self.read_thread is not None:
            self.read_thread.join(timeout=1.0)
            self.read_thread = None
        
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        
        # Cleanup temporary files
        if self._temp_file and os.path.exists(self._temp_file):
            try:
                os.remove(self._temp_file)
            except:
                pass
            self._temp_file = None
        
        # Clear image list
        self.image_list.clear()
        self.image_index = 0
        
        # Clear queue
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except:
                pass
    
    def get_progress(self) -> float:
        """
        Get processing progress (0-1).
        
        Returns:
            Progress as float between 0 and 1.
        """
        if self.total_frames <= 0:
            return 0.0
        return min(self.frame_count / self.total_frames, 1.0)
    
    def seek(self, frame_number: int) -> bool:
        """
        Seek to specific frame number.
        
        Args:
            frame_number: Target frame number.
            
        Returns:
            True if successful.
        """
        if self.cap is None:
            return False
        
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        self.frame_count = frame_number
        return True
    
    def get_info(self) -> Dict[str, Any]:
        """Get video information."""
        return {
            'source': str(self.original_source),
            'source_type': self.source_type,
            'is_live': self.is_live,
            'width': self.original_width,
            'height': self.original_height,
            'fps': self.original_fps,
            'total_frames': self.total_frames,
            'duration_seconds': self.total_frames / self.original_fps if self.original_fps > 0 and not self.is_live else 0
        }
    
    def __enter__(self):
        """Context manager entry."""
        self.open()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class VideoWriter:
    """
    Video writer for saving processed frames.
    """
    
    def __init__(
        self,
        output_path: str,
        fps: float = 30.0,
        width: Optional[int] = None,
        height: Optional[int] = None,
        codec: str = 'mp4v'
    ):
        """
        Initialize video writer.
        
        Args:
            output_path: Output file path.
            fps: Frames per second.
            width: Frame width.
            height: Frame height.
            codec: Video codec (e.g., 'mp4v', 'XVID').
        """
        self.output_path = Path(output_path)
        self.fps = fps
        self.width = width
        self.height = height
        self.codec = codec
        
        self.writer: Optional[cv2.VideoWriter] = None
        self.frame_count = 0
    
    def open(self) -> bool:
        """Open video writer."""
        try:
            if self.width is None or self.height is None:
                return False

            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            
            fourcc = cv2.VideoWriter_fourcc(*self.codec)
            self.writer = cv2.VideoWriter(
                str(self.output_path),
                fourcc,
                self.fps,
                (self.width, self.height)
            )
            
            return self.writer.isOpened()
        except Exception as e:
            print(f"Error opening video writer: {e}")
            return False
    
    def write(self, frame: np.ndarray) -> None:
        """Write a frame to the video."""
        if self.width is None or self.height is None:
            self.height, self.width = frame.shape[:2]

        if self.writer is None:
            if not self.open():
                return
        
        # Resize if needed
        if frame.shape[1] != self.width or frame.shape[0] != self.height:
            frame = cv2.resize(frame, (self.width, self.height))
        
        self.writer.write(frame)
        self.frame_count += 1
    
    def close(self) -> None:
        """Close video writer."""
        if self.writer is not None:
            self.writer.release()
            self.writer = None
            print(f"Video saved: {self.output_path} ({self.frame_count} frames)")
    
    def __enter__(self):
        """Context manager entry."""
        self.open()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
