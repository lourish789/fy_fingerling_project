#!/usr/bin/env python
"""
Catfish Fingerling Counter - Main Entry Point

Count and sort catfish fingerlings by class from video, camera, images, or URLs.

Usage Examples:
    # Process video file
    python main.py --source video.mp4
    
    # Live camera feed
    python main.py --source 0
    
    # YouTube or web video URL
    python main.py --source "https://youtube.com/watch?v=..."
    
    # Process single image
    python main.py --image fingerlings.jpg
    
    # Process directory of images
    python main.py --image-dir ./images
    
    # Run web server for uploads
    python main.py --web-server
    
    # Save output video
    python main.py --source video.mp4 --output counted_video.mp4

Streaming Dashboard:
    Open http://localhost:5000 in your browser for real-time monitoring
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from app.counter import main

if __name__ == '__main__':
    sys.exit(main())
