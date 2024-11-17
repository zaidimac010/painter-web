import React, { useEffect, useRef, useState, forwardRef, useImperativeHandle } from 'react';
import { motion } from 'framer-motion';

interface Point {
  x: number;
  y: number;
}

interface CanvasState {
  imageData: ImageData;
  tool: 'pen' | 'eraser';
  color: string;
  size: number;
}

interface Media {
  element: HTMLImageElement | HTMLVideoElement;
  x: number;
  y: number;
  width: number;
  height: number;
  aspectRatio: number;
  isMoving: boolean;
  isResizing: boolean;
  type: 'image' | 'video';
  isPlaying?: boolean;
}

interface CanvasProps {
  tool: 'pen' | 'eraser';
  brushColor: string;
  brushSize: number;
  onImageUpload?: (file: File) => void;
  onVideoUpload?: (file: File) => void;
}

interface ResizeHandle {
  position: 'topLeft' | 'topRight' | 'bottomLeft' | 'bottomRight';
  cursor: string;
}

const resizeHandles: ResizeHandle[] = [
  { position: 'topLeft', cursor: 'nw-resize' },
  { position: 'topRight', cursor: 'ne-resize' },
  { position: 'bottomLeft', cursor: 'sw-resize' },
  { position: 'bottomRight', cursor: 'se-resize' }
];

const Canvas = forwardRef<any, CanvasProps>(({ tool, brushColor, brushSize, onImageUpload, onVideoUpload }, ref) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const contextRef = useRef<CanvasRenderingContext2D | null>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [lastPoint, setLastPoint] = useState<Point | null>(null);
  const [undoStack, setUndoStack] = useState<CanvasState[]>([]);
  const [redoStack, setRedoStack] = useState<CanvasState[]>([]);
  const [cursor, setCursor] = useState<string>('default');
  const [media, setMedia] = useState<Media[]>([]);
  const [selectedMedia, setSelectedMedia] = useState<number | null>(null);
  const [activeHandle, setActiveHandle] = useState<string | null>(null);

  // Initialize canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    const parent = canvas?.parentElement;
    if (!canvas || !parent) return;

    // Create a temporary canvas to store the current drawing
    const tempCanvas = document.createElement('canvas');
    const tempCtx = tempCanvas.getContext('2d');
    if (tempCtx && contextRef.current) {
      tempCanvas.width = canvas.width;
      tempCanvas.height = canvas.height;
      tempCtx.drawImage(canvas, 0, 0);
    }

    const resizeCanvas = () => {
      // Get the display size of the canvas
      const displayWidth = parent.clientWidth;
      const displayHeight = parent.clientHeight;

      // Calculate the device pixel ratio
      const dpr = window.devicePixelRatio || 1;

      // Set the canvas size to match the display size multiplied by the device pixel ratio
      canvas.width = displayWidth * dpr;
      canvas.height = displayHeight * dpr;

      // Set the display size through CSS
      canvas.style.width = `${displayWidth}px`;
      canvas.style.height = `${displayHeight}px`;

      // Get the context and scale it according to the device pixel ratio
      const ctx = canvas.getContext('2d', {
        willReadFrequently: true,
        alpha: true
      }) as CanvasRenderingContext2D;

      if (!ctx) return;

      // Scale all drawing operations by the device pixel ratio
      ctx.scale(dpr, dpr);

      // Enable high-quality image rendering
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';

      // Set up drawing properties
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.strokeStyle = brushColor;
      ctx.lineWidth = brushSize;

      if (!contextRef.current) {
        // Initialize with white background
        ctx.fillStyle = 'white';
        ctx.fillRect(0, 0, displayWidth, displayHeight);
        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        setUndoStack([{ imageData, tool: 'pen', color: brushColor, size: brushSize }]);
      } else if (tempCtx) {
        // Restore the previous drawing, scaling it to the new size
        ctx.drawImage(tempCanvas, 0, 0, displayWidth, displayHeight);
      }

      contextRef.current = ctx;
    };

    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);
    return () => window.removeEventListener('resize', resizeCanvas);
  }, [brushColor, brushSize]);

  // Separate effect for updating brush properties
  useEffect(() => {
    if (contextRef.current) {
      requestAnimationFrame(() => {
        if (!contextRef.current) return;

        contextRef.current.strokeStyle = tool === 'eraser' ? '#FFFFFF' : brushColor;
        contextRef.current.lineWidth = brushSize;
        contextRef.current.globalCompositeOperation = tool === 'eraser' ? 'destination-out' : 'source-over';

        // Update cursor based on tool and size
        const cursorSize = Math.max(brushSize, 10);
        const cursorColor = tool === 'eraser' ? '#000000' : brushColor;
        const cursorSvg = `
          <svg xmlns="http://www.w3.org/2000/svg" width="${cursorSize}" height="${cursorSize}" viewBox="0 0 ${cursorSize} ${cursorSize}" fill="none">
            <circle cx="${cursorSize/2}" cy="${cursorSize/2}" r="${cursorSize/2-1}" stroke="white" stroke-width="2"/>
            <circle cx="${cursorSize/2}" cy="${cursorSize/2}" r="${cursorSize/2-1}" stroke="${encodeURIComponent(cursorColor)}" stroke-width="1"/>
          </svg>
        `.trim().replace(/\s+/g, ' ');

        setCursor(`url('data:image/svg+xml;utf8,${cursorSvg}') ${cursorSize/2} ${cursorSize/2}, auto`);
      });
    }
  }, [brushSize, brushColor, tool]);

  const getCoordinates = (event: React.MouseEvent | React.TouchEvent): Point | null => {
    if (!canvasRef.current) return null;

    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();

    if ('touches' in event) {
      const touch = event.touches[0];
      return {
        x: touch.clientX - rect.left,
        y: touch.clientY - rect.top
      };
    } else {
      return {
        x: event.clientX - rect.left,
        y: event.clientY - rect.top
      };
    }
  };

  const startDrawing = (event: React.MouseEvent | React.TouchEvent) => {
    event.preventDefault();
    const point = getCoordinates(event);
    if (!point || !contextRef.current) return;

    setIsDrawing(true);
    contextRef.current.beginPath();
    contextRef.current.moveTo(point.x, point.y);
    setLastPoint(point);
  };

  const draw = (event: React.MouseEvent | React.TouchEvent) => {
    event.preventDefault();
    if (!isDrawing || !lastPoint || !contextRef.current) return;

    const point = getCoordinates(event);
    if (!point) return;

    const ctx = contextRef.current;

    // Use quadratic curves for smoother lines
    ctx.beginPath();
    ctx.moveTo(lastPoint.x, lastPoint.y);

    // Calculate control point
    const controlX = (lastPoint.x + point.x) / 2;
    const controlY = (lastPoint.y + point.y) / 2;

    // Draw a quadratic curve
    ctx.quadraticCurveTo(controlX, controlY, point.x, point.y);
    ctx.stroke();

    setLastPoint(point);
  };

  const stopDrawing = () => {
    if (isDrawing) {
      saveState();
    }
    setIsDrawing(false);
    setLastPoint(null);
  };

  const saveState = () => {
    if (!canvasRef.current || !contextRef.current) return;

    const imageData = contextRef.current.getImageData(
      0,
      0,
      canvasRef.current.width,
      canvasRef.current.height
    );

    setUndoStack(prev => [...prev, { imageData, tool, color: brushColor, size: brushSize }]);
    setRedoStack([]);
  };

  const undo = () => {
    if (undoStack.length <= 1) return;

    const currentState = undoStack[undoStack.length - 1];
    const previousState = undoStack[undoStack.length - 2];

    setRedoStack(prev => [...prev, currentState]);
    setUndoStack(prev => prev.slice(0, -1));

    if (!canvasRef.current || !contextRef.current) return;

    // Restore previous state
    contextRef.current.globalCompositeOperation = 'source-over';
    contextRef.current.putImageData(previousState.imageData, 0, 0);

    // Restore tool settings
    contextRef.current.strokeStyle = previousState.tool === 'eraser' ? '#FFFFFF' : previousState.color;
    contextRef.current.lineWidth = previousState.size;
    contextRef.current.globalCompositeOperation = previousState.tool === 'eraser' ? 'destination-out' : 'source-over';
  };

  const redo = () => {
    if (redoStack.length === 0) return;

    const nextState = redoStack[redoStack.length - 1];

    setUndoStack(prev => [...prev, nextState]);
    setRedoStack(prev => prev.slice(0, -1));

    if (!canvasRef.current || !contextRef.current) return;

    // Restore next state
    contextRef.current.globalCompositeOperation = 'source-over';
    contextRef.current.putImageData(nextState.imageData, 0, 0);

    // Restore tool settings
    contextRef.current.strokeStyle = nextState.tool === 'eraser' ? '#FFFFFF' : nextState.color;
    contextRef.current.lineWidth = nextState.size;
    contextRef.current.globalCompositeOperation = nextState.tool === 'eraser' ? 'destination-out' : 'source-over';
  };

  const clear = () => {
    if (!canvasRef.current || !contextRef.current) return;

    const canvas = canvasRef.current;

    // Save current context state
    const currentState = {
      imageData: contextRef.current.getImageData(0, 0, canvas.width, canvas.height),
      tool,
      color: brushColor,
      size: brushSize
    };

    // Clear canvas
    contextRef.current.globalCompositeOperation = 'source-over';
    contextRef.current.fillStyle = 'white';
    contextRef.current.fillRect(0, 0, canvas.width, canvas.height);

    // Restore tool settings
    contextRef.current.strokeStyle = tool === 'eraser' ? '#FFFFFF' : brushColor;
    contextRef.current.lineWidth = brushSize;
    contextRef.current.globalCompositeOperation = tool === 'eraser' ? 'destination-out' : 'source-over';

    // Save state
    setUndoStack(prev => [...prev, currentState]);
    setRedoStack([]);
  };

  const addMedia = (element: HTMLImageElement | HTMLVideoElement, type: 'image' | 'video') => {
    const aspectRatio = element.width / element.height;
    const maxWidth = canvasRef.current!.width * 0.8;
    const maxHeight = canvasRef.current!.height * 0.8;

    let width = element.width;
    let height = element.height;

    if (width > maxWidth) {
      width = maxWidth;
      height = width / aspectRatio;
    }
    if (height > maxHeight) {
      height = maxHeight;
      width = height * aspectRatio;
    }

    const x = (canvasRef.current!.width - width) / 2;
    const y = (canvasRef.current!.height - height) / 2;

    const newMedia: Media = {
      element,
      x,
      y,
      width,
      height,
      aspectRatio,
      isMoving: false,
      isResizing: false,
      type,
      isPlaying: false
    };

    setMedia(prev => [...prev, newMedia]);
    setSelectedMedia(media.length);
  };

  const handleVideoPlayback = (index: number) => {
    if (index === selectedMedia) {
      setMedia(prev => {
        const newMedia = [...prev];
        const item = newMedia[index];
        if (item.type === 'video') {
          const video = item.element as HTMLVideoElement;
          if (video.paused) {
            video.play();
            item.isPlaying = true;
          } else {
            video.pause();
            item.isPlaying = false;
          }
        }
        return newMedia;
      });
    }
  };

  const handleImageUpload = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        addMedia(img, 'image');
      };
      img.src = e.target?.result as string;
    };
    reader.readAsDataURL(file);
  };

  const handleVideoUpload = (file: File) => {
    const video = document.createElement('video');
    video.src = URL.createObjectURL(file);
    video.autoplay = false;
    video.loop = true;
    video.muted = true;

    video.onloadedmetadata = () => {
      addMedia(video, 'video');
    };
  };

  const getResizeHandlePosition = (mediaItem: Media, handle: ResizeHandle) => {
    switch (handle.position) {
      case 'topLeft':
        return { x: mediaItem.x, y: mediaItem.y };
      case 'topRight':
        return { x: mediaItem.x + mediaItem.width, y: mediaItem.y };
      case 'bottomLeft':
        return { x: mediaItem.x, y: mediaItem.y + mediaItem.height };
      case 'bottomRight':
        return { x: mediaItem.x + mediaItem.width, y: mediaItem.y + mediaItem.height };
    }
  };

  const isPointInResizeHandle = (point: Point, mediaItem: Media) => {
    const handleSize = 12;
    for (const handle of resizeHandles) {
      const pos = getResizeHandlePosition(mediaItem, handle);
      if (
        point.x >= pos.x - handleSize/2 &&
        point.x <= pos.x + handleSize/2 &&
        point.y >= pos.y - handleSize/2 &&
        point.y <= pos.y + handleSize/2
      ) {
        return handle.position;
      }
    }
    return null;
  };

  const handleMouseMove = (event: React.MouseEvent) => {
    const point = getCoordinates(event);
    if (!point) return;

    let newCursor = 'default';

    // Check if near any media's resize handles
    for (let i = media.length - 1; i >= 0; i--) {
      const item = media[i];

      // Only show resize cursors for selected media
      if (i === selectedMedia) {
        for (const handle of resizeHandles) {
          const pos = getResizeHandlePosition(item, handle);
          const handleSize = 12;

          if (
            point.x >= pos.x - handleSize/2 &&
            point.x <= pos.x + handleSize/2 &&
            point.y >= pos.y - handleSize/2 &&
            point.y <= pos.y + handleSize/2
          ) {
            newCursor = handle.cursor;
            break;
          }
        }
      }

      // Show appropriate cursor when over media
      if (
        point.x >= item.x &&
        point.x <= item.x + item.width &&
        point.y >= item.y &&
        point.y <= item.y + item.height
      ) {
        if (newCursor === 'default') {
          if (i === selectedMedia) {
            newCursor = item.type === 'video' ? 'pointer' : 'move';
          } else {
            newCursor = 'move';
          }
        }
        break;
      }
    }

    setCursor(newCursor);

    // Handle media movement/resizing
    if (selectedMedia !== null) {
      const item = media[selectedMedia];

      if (item.isResizing && activeHandle) {
        const minSize = 50;
        let newWidth = item.width;
        let newHeight = item.height;
        let newX = item.x;
        let newY = item.y;

        switch (activeHandle) {
          case 'topLeft': {
            newWidth = Math.max(minSize, item.x + item.width - point.x);
            newHeight = newWidth / item.aspectRatio;
            newX = Math.min(item.x + item.width - minSize, point.x);
            newY = item.y + item.height - newHeight;
            break;
          }
          case 'topRight': {
            newWidth = Math.max(minSize, point.x - item.x);
            newHeight = newWidth / item.aspectRatio;
            newY = item.y + item.height - newHeight;
            break;
          }
          case 'bottomLeft': {
            newWidth = Math.max(minSize, item.x + item.width - point.x);
            newHeight = newWidth / item.aspectRatio;
            newX = Math.min(item.x + item.width - minSize, point.x);
            break;
          }
          case 'bottomRight': {
            newWidth = Math.max(minSize, point.x - item.x);
            newHeight = newWidth / item.aspectRatio;
            break;
          }
        }

        // Keep media within canvas bounds
        if (newX < 0) {
          const diff = -newX;
          newX = 0;
          newWidth -= diff;
          newHeight = newWidth / item.aspectRatio;
        }
        if (newY < 0) {
          const diff = -newY;
          newY = 0;
          newHeight -= diff;
          newWidth = newHeight * item.aspectRatio;
        }
        if (newX + newWidth > canvasRef.current!.width) {
          newWidth = canvasRef.current!.width - newX;
          newHeight = newWidth / item.aspectRatio;
        }
        if (newY + newHeight > canvasRef.current!.height) {
          newHeight = canvasRef.current!.height - newY;
          newWidth = newHeight * item.aspectRatio;
        }

        setMedia(prev => {
          const newMedia = [...prev];
          newMedia[selectedMedia] = {
            ...item,
            x: newX,
            y: newY,
            width: newWidth,
            height: newHeight
          };
          return newMedia;
        });
      }

      if (item.isMoving) {
        const newX = point.x - item.width / 2;
        const newY = point.y - item.height / 2;

        // Keep media within canvas bounds
        const boundedX = Math.max(0, Math.min(newX, canvasRef.current!.width - item.width));
        const boundedY = Math.max(0, Math.min(newY, canvasRef.current!.height - item.height));

        setMedia(prev => {
          const newMedia = [...prev];
          newMedia[selectedMedia] = {
            ...item,
            x: boundedX,
            y: boundedY
          };
          return newMedia;
        });
      }
    }

    // Handle drawing
    if (isDrawing) {
      draw(event);
    }
  };

  const handleMouseDown = (event: React.MouseEvent) => {
    const point = getCoordinates(event);
    if (!point) return;

    let handled = false;

    // Check media interactions in reverse order (top to bottom)
    for (let i = media.length - 1; i >= 0; i--) {
      const item = media[i];

      // Check resize handles for selected media
      if (i === selectedMedia) {
        const handlePosition = isPointInResizeHandle(point, item);
        if (handlePosition) {
          setActiveHandle(handlePosition);
          setMedia(prev => prev.map((m, index) => 
            index === i ? { ...m, isResizing: true, isMoving: false } : { ...m, isResizing: false, isMoving: false }
          ));
          handled = true;
          break;
        }
      }

      // Check if clicked on media
      if (
        point.x >= item.x &&
        point.x <= item.x + item.width &&
        point.y >= item.y &&
        point.y <= item.y + item.height
      ) {
        if (i === selectedMedia && item.type === 'video') {
          handleVideoPlayback(i);
        } else {
          setSelectedMedia(i);
          setActiveHandle(null);
          setMedia(prev => prev.map((m, index) => 
            index === i ? { ...m, isMoving: true, isResizing: false } : { ...m, isMoving: false, isResizing: false }
          ));
        }
        handled = true;
        break;
      }
    }

    if (!handled) {
      setSelectedMedia(null);
      setActiveHandle(null);
      setMedia(prev => prev.map(m => ({ ...m, isMoving: false, isResizing: false })));
      startDrawing(event);
    }
  };

  const handleMediaMouseUp = () => {
    setMedia(prev => prev.map(item => ({
      ...item,
      isMoving: false,
      isResizing: false
    })));
    setActiveHandle(null);
  };

  // Draw media on canvas
  useEffect(() => {
    if (!contextRef.current || !canvasRef.current) return;

    const ctx = contextRef.current;

    const render = () => {
      // Clear the entire canvas
      ctx.clearRect(0, 0, canvasRef.current!.width, canvasRef.current!.height);

      // Redraw the background if needed
      if (undoStack.length > 0) {
        const lastState = undoStack[undoStack.length - 1];
        ctx.putImageData(lastState.imageData, 0, 0);
      }

      // Draw all media
      media.forEach((item, index) => {
        // Draw the media
        ctx.drawImage(item.element, item.x, item.y, item.width, item.height);

        // Draw selection border and handles if selected
        if (index === selectedMedia) {
          // Draw selection border with shadow effect
          ctx.save();
          ctx.strokeStyle = '#2196f3';
          ctx.lineWidth = 2;
          ctx.shadowColor = 'rgba(33, 150, 243, 0.3)';
          ctx.shadowBlur = 5;
          ctx.strokeRect(item.x, item.y, item.width, item.height);
          ctx.restore();

          // Draw resize handles
          resizeHandles.forEach(handle => {
            const pos = getResizeHandlePosition(item, handle);
            const handleSize = 12;

            // Draw handle shadow
            ctx.save();
            ctx.shadowColor = 'rgba(0, 0, 0, 0.2)';
            ctx.shadowBlur = 4;
            ctx.shadowOffsetX = 1;
            ctx.shadowOffsetY = 1;

            // Draw white background
            ctx.fillStyle = 'white';
            ctx.beginPath();
            ctx.arc(pos.x, pos.y, handleSize/2, 0, Math.PI * 2);
            ctx.fill();

            // Draw border
            ctx.strokeStyle = '#2196f3';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(pos.x, pos.y, handleSize/2, 0, Math.PI * 2);
            ctx.stroke();

            ctx.restore();
          });
        }
      });
    };

    render();
  }, [media, selectedMedia, undoStack]);

  useImperativeHandle(ref, () => ({
    undo,
    redo,
    clear,
    handleImageUpload,
    handleVideoUpload
  }));

  return (
    <motion.div 
      className="w-full h-full relative rounded-3xl overflow-hidden"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMediaMouseUp}
      onMouseLeave={handleMediaMouseUp}
    >
      <canvas
        ref={canvasRef}
        style={{
          cursor: cursor,
          width: '100%',
          height: '100%',
          touchAction: 'none'
        }}
        className="touch-none bg-white rounded-3xl"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={stopDrawing}
        onMouseLeave={stopDrawing}
        onTouchStart={startDrawing}
        onTouchMove={draw}
        onTouchEnd={stopDrawing}
        onTouchCancel={stopDrawing}
      />
    </motion.div>
  );
});

export default Canvas;
