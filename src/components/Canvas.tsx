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

const Canvas = forwardRef<any, CanvasProps>(({ tool, brushColor, brushSize }, ref) => {
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
  const [isInitialized, setIsInitialized] = useState(false);

  useEffect(() => {
    if (!canvasRef.current || isInitialized) return;

    const canvas = canvasRef.current;
    const parent = canvas.parentElement;
    if (!parent) return;

    const dpr = window.devicePixelRatio || 1;
    const displayWidth = parent.clientWidth;
    const displayHeight = parent.clientHeight;

    canvas.width = displayWidth * dpr;
    canvas.height = displayHeight * dpr;
    canvas.style.width = `${displayWidth}px`;
    canvas.style.height = `${displayHeight}px`;

    const ctx = canvas.getContext('2d', {
      willReadFrequently: true,
      alpha: true
    });

    if (!ctx) return;

    ctx.scale(dpr, dpr);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = tool === 'eraser' ? '#FFFFFF' : brushColor;
    ctx.lineWidth = brushSize;
    ctx.globalCompositeOperation = tool === 'eraser' ? 'destination-out' : 'source-over';

    contextRef.current = ctx;

    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    setUndoStack([{ 
      imageData, 
      tool: 'pen', 
      color: brushColor, 
      size: brushSize 
    }]);

    setIsInitialized(true);
  }, [brushColor, brushSize, tool, isInitialized]);

  useEffect(() => {
    const handleResize = () => {
      if (!canvasRef.current || !contextRef.current || !isInitialized) return;

      const canvas = canvasRef.current;
      const parent = canvas.parentElement;
      if (!parent) return;

      const tempCanvas = document.createElement('canvas');
      const tempCtx = tempCanvas.getContext('2d');
      if (tempCtx) {
        tempCanvas.width = canvas.width;
        tempCanvas.height = canvas.height;
        tempCtx.drawImage(canvas, 0, 0);
      }

      const dpr = window.devicePixelRatio || 1;
      const displayWidth = parent.clientWidth;
      const displayHeight = parent.clientHeight;

      canvas.width = displayWidth * dpr;
      canvas.height = displayHeight * dpr;
      canvas.style.width = `${displayWidth}px`;
      canvas.style.height = `${displayHeight}px`;

      const ctx = contextRef.current;
      ctx.scale(dpr, dpr);
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.strokeStyle = tool === 'eraser' ? '#FFFFFF' : brushColor;
      ctx.lineWidth = brushSize;
      ctx.globalCompositeOperation = tool === 'eraser' ? 'destination-out' : 'source-over';

      if (tempCtx) {
        ctx.drawImage(tempCanvas, 0, 0, displayWidth, displayHeight);
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [brushColor, brushSize, tool, isInitialized]);

  const saveState = () => {
    if (!canvasRef.current || !contextRef.current) return;

    const imageData = contextRef.current.getImageData(
      0,
      0,
      canvasRef.current.width,
      canvasRef.current.height
    );

    setUndoStack(prev => [...prev, { 
      imageData, 
      tool, 
      color: brushColor, 
      size: brushSize 
    }]);
    setRedoStack([]);
  };

  const undo = () => {
    if (!canvasRef.current || !contextRef.current || undoStack.length === 0) return;

    const currentState = undoStack[undoStack.length - 1];
    
    if (undoStack.length > 1) {
      const previousState = undoStack[undoStack.length - 2];
      
      setRedoStack(prev => [...prev, currentState]);
      setUndoStack(prev => prev.slice(0, -1));

      contextRef.current.globalCompositeOperation = 'source-over';
      contextRef.current.putImageData(previousState.imageData, 0, 0);
    } else {
      contextRef.current.globalCompositeOperation = 'source-over';
      contextRef.current.fillStyle = '#FFFFFF';
      contextRef.current.fillRect(0, 0, canvasRef.current.width, canvasRef.current.height);
      
      const imageData = contextRef.current.getImageData(
        0,
        0,
        canvasRef.current.width,
        canvasRef.current.height
      );
      
      setRedoStack(prev => [...prev, currentState]);
      setUndoStack(prev => [{
        imageData,
        tool: 'pen',
        color: brushColor,
        size: brushSize
      }]);
    }
  };

  const redo = () => {
    if (!canvasRef.current || !contextRef.current || redoStack.length === 0) return;

    const nextState = redoStack[redoStack.length - 1];
    
    setUndoStack(prev => [...prev, nextState]);
    setRedoStack(prev => prev.slice(0, -1));

    contextRef.current.globalCompositeOperation = 'source-over';
    contextRef.current.putImageData(nextState.imageData, 0, 0);
  };

  const clear = () => {
    if (!canvasRef.current || !contextRef.current) return;

    const currentState = {
      imageData: contextRef.current.getImageData(
        0,
        0,
        canvasRef.current.width,
        canvasRef.current.height
      ),
      tool,
      color: brushColor,
      size: brushSize
    };

    contextRef.current.globalCompositeOperation = 'source-over';
    contextRef.current.fillStyle = '#FFFFFF';
    contextRef.current.fillRect(0, 0, canvasRef.current.width, canvasRef.current.height);

    const clearedImageData = contextRef.current.getImageData(
      0,
      0,
      canvasRef.current.width,
      canvasRef.current.height
    );

    setUndoStack(prev => [...prev, currentState, {
      imageData: clearedImageData,
      tool: 'pen',
      color: brushColor,
      size: brushSize
    }]);
    setRedoStack([]);
  };

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

    ctx.beginPath();
    ctx.moveTo(lastPoint.x, lastPoint.y);

    const controlX = (lastPoint.x + point.x) / 2;
    const controlY = (lastPoint.y + point.y) / 2;

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

    for (let i = media.length - 1; i >= 0; i--) {
      const item = media[i];

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

    if (isDrawing) {
      draw(event);
    }
  };

  const handleMouseDown = (event: React.MouseEvent) => {
    const point = getCoordinates(event);
    if (!point) return;

    let handled = false;

    for (let i = media.length - 1; i >= 0; i--) {
      const item = media[i];

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

  useEffect(() => {
    if (!contextRef.current || !canvasRef.current) return;

    const ctx = contextRef.current;

    const render = () => {
      ctx.clearRect(0, 0, canvasRef.current!.width, canvasRef.current!.height);

      if (undoStack.length > 0) {
        const lastState = undoStack[undoStack.length - 1];
        ctx.putImageData(lastState.imageData, 0, 0);
      }

      media.forEach((item, index) => {
        ctx.drawImage(item.element, item.x, item.y, item.width, item.height);

        if (index === selectedMedia) {
          ctx.save();
          ctx.strokeStyle = '#2196f3';
          ctx.lineWidth = 2;
          ctx.shadowColor = 'rgba(33, 150, 243, 0.3)';
          ctx.shadowBlur = 5;
          ctx.strokeRect(item.x, item.y, item.width, item.height);
          ctx.restore();

          resizeHandles.forEach(handle => {
            const pos = getResizeHandlePosition(item, handle);
            const handleSize = 12;

            ctx.save();
            ctx.shadowColor = 'rgba(0, 0, 0, 0.2)';
            ctx.shadowBlur = 4;
            ctx.shadowOffsetX = 1;
            ctx.shadowOffsetY = 1;

            ctx.fillStyle = 'white';
            ctx.beginPath();
            ctx.arc(pos.x, pos.y, handleSize/2, 0, Math.PI * 2);
            ctx.fill();

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
    undo: () => {
      requestAnimationFrame(() => {
        undo();
      });
    },
    redo: () => {
      requestAnimationFrame(() => {
        redo();
      });
    },
    clear: () => {
      requestAnimationFrame(() => {
        clear();
      });
    },
    handleImageUpload,
    handleVideoUpload
  }), [undo, redo, clear, handleImageUpload, handleVideoUpload]);

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
