import React, { useEffect, useRef, useState, forwardRef, useImperativeHandle, useCallback, useMemo } from 'react';
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

interface CanvasProps {
  tool: 'pen' | 'eraser';
  brushColor: string;
  brushSize: number;
}

const Canvas = forwardRef<any, CanvasProps>(({ tool, brushColor, brushSize }, ref) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const contextRef = useRef<CanvasRenderingContext2D | null>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [lastPoint, setLastPoint] = useState<Point | null>(null);
  const [undoStack, setUndoStack] = useState<CanvasState[]>([]);
  const [redoStack, setRedoStack] = useState<CanvasState[]>([]);
  const [isInitialized, setIsInitialized] = useState(false);
  const dprRef = useRef(window.devicePixelRatio || 1);

  const updateBrushStyle = useCallback((ctx: CanvasRenderingContext2D) => {
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = tool === 'eraser' ? '#FFFFFF' : brushColor;
    ctx.lineWidth = brushSize;
    ctx.globalCompositeOperation = tool === 'eraser' ? 'destination-out' : 'source-over';
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
  }, [tool, brushColor, brushSize]);

  const handleResize = useCallback(() => {
    if (!canvasRef.current || !contextRef.current || !isInitialized) return;

    const canvas = canvasRef.current;
    const parent = canvas.parentElement;
    if (!parent) return;

    const dpr = dprRef.current;
    const rect = parent.getBoundingClientRect();

    // Create a temporary canvas to store the current drawing
    const tempCanvas = document.createElement('canvas');
    const tempCtx = tempCanvas.getContext('2d');
    if (!tempCtx) return;

    tempCanvas.width = canvas.width;
    tempCanvas.height = canvas.height;
    tempCtx.drawImage(canvas, 0, 0);

    // Resize the main canvas
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;

    const ctx = contextRef.current;
    ctx.scale(dpr, dpr);
    updateBrushStyle(ctx);

    // Draw back the content
    ctx.drawImage(tempCanvas, 0, 0, rect.width, rect.height);
  }, [updateBrushStyle, isInitialized]);

  useEffect(() => {
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [handleResize]);

  useEffect(() => {
    if (!canvasRef.current || isInitialized) return;

    const canvas = canvasRef.current;
    const parent = canvas.parentElement;
    if (!parent) return;

    const dpr = dprRef.current;
    const rect = parent.getBoundingClientRect();
    
    // Set the canvas size in pixels
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    
    // Set the display size in CSS pixels
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;

    const ctx = canvas.getContext('2d', {
      willReadFrequently: true,
      alpha: false
    });

    if (!ctx) return;

    // Scale all drawing operations by the dpr
    ctx.scale(dpr, dpr);
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(0, 0, rect.width, rect.height);
    
    contextRef.current = ctx;
    updateBrushStyle(ctx);

    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    setUndoStack([{ 
      imageData, 
      tool: 'pen', 
      color: brushColor, 
      size: brushSize 
    }]);

    setIsInitialized(true);
  }, [brushColor, brushSize, tool, isInitialized, updateBrushStyle]);

  useEffect(() => {
    if (!contextRef.current) return;
    updateBrushStyle(contextRef.current);
  }, [updateBrushStyle]);

  const getCoordinates = useCallback((event: React.MouseEvent | React.TouchEvent): Point | null => {
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
  }, []);

  const startDrawing = useCallback((event: React.MouseEvent | React.TouchEvent) => {
    event.preventDefault();
    const point = getCoordinates(event);
    if (!point || !contextRef.current) return;

    const ctx = contextRef.current;
    ctx.beginPath();
    
    setIsDrawing(true);
    setLastPoint(point);
  }, [getCoordinates]);

  const draw = useCallback((event: React.MouseEvent | React.TouchEvent) => {
    event.preventDefault();
    if (!isDrawing || !lastPoint || !contextRef.current) return;

    const point = getCoordinates(event);
    if (!point) return;

    const ctx = contextRef.current;

    ctx.beginPath();
    ctx.moveTo(lastPoint.x, lastPoint.y);
    ctx.lineTo(point.x, point.y);
    ctx.stroke();

    setLastPoint(point);
  }, [isDrawing, lastPoint, getCoordinates]);

  const saveState = useCallback(() => {
    if (!contextRef.current || !canvasRef.current) return;
    
    const canvas = canvasRef.current;
    const imageData = contextRef.current.getImageData(0, 0, canvas.width, canvas.height);
    
    setUndoStack(prev => [...prev, {
      imageData,
      tool,
      color: brushColor,
      size: brushSize
    }]);
    setRedoStack([]);
  }, [tool, brushColor, brushSize]);

  const stopDrawing = useCallback(() => {
    if (isDrawing) {
      saveState();
    }
    setIsDrawing(false);
    setLastPoint(null);
  }, [isDrawing, saveState]);

  const undo = useCallback(() => {
    if (undoStack.length <= 1) return;
    
    const canvas = canvasRef.current;
    const ctx = contextRef.current;
    if (!canvas || !ctx) return;
    
    const currentState = undoStack[undoStack.length - 1];
    const previousState = undoStack[undoStack.length - 2];
    
    ctx.putImageData(previousState.imageData, 0, 0);
    setRedoStack(prev => [...prev, currentState]);
    setUndoStack(prev => prev.slice(0, -1));
  }, [undoStack]);

  const redo = useCallback(() => {
    if (redoStack.length === 0) return;
    
    const ctx = contextRef.current;
    if (!ctx) return;
    
    const nextState = redoStack[redoStack.length - 1];
    ctx.putImageData(nextState.imageData, 0, 0);
    
    setUndoStack(prev => [...prev, nextState]);
    setRedoStack(prev => prev.slice(0, -1));
  }, [redoStack]);

  const clear = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = contextRef.current;
    if (!canvas || !ctx) return;
    
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    saveState();
  }, [saveState]);

  const api = useMemo(() => ({
    undo,
    redo,
    clear
  }), [undo, redo, clear]);

  useImperativeHandle(ref, () => api);

  return (
    <motion.div 
      className="w-full h-full relative rounded-3xl overflow-hidden"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      <canvas
        ref={canvasRef}
        style={{
          cursor: tool === 'eraser' ? 'crosshair' : 'default',
          width: '100%',
          height: '100%',
          touchAction: 'none'
        }}
        className="touch-none bg-white rounded-3xl"
        onMouseDown={startDrawing}
        onMouseMove={draw}
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
