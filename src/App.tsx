import React, { useState, useRef } from 'react';
import Canvas from './components/Canvas';
import Toolbar from './components/Toolbar';

const App = () => {
  const [tool, setTool] = useState<'pen' | 'eraser'>('pen');
  const [color, setColor] = useState('#000000');
  const [size, setSize] = useState(5);
  const canvasRef = useRef<any>(null);

  const handleUndo = () => {
    canvasRef.current?.undo();
  };

  const handleRedo = () => {
    canvasRef.current?.redo();
  };

  const handleClear = () => {
    canvasRef.current?.clear();
  };

  const handleImageUpload = (file: File) => {
    canvasRef.current?.handleImageUpload(file);
  };

  const handleVideoUpload = (file: File) => {
    canvasRef.current?.handleVideoUpload(file);
  };

  return (
    <div className="relative w-screen h-screen bg-gradient-to-br from-indigo-50 to-pink-50 overflow-hidden">
      <Canvas 
        ref={canvasRef}
        tool={tool}
        brushColor={color}
        brushSize={size}
      />
      <Toolbar
        currentTool={tool}
        currentColor={color}
        currentSize={size}
        onToolChange={setTool}
        onColorChange={setColor}
        onSizeChange={setSize}
        onUndo={handleUndo}
        onRedo={handleRedo}
        onClear={handleClear}
        onImageUpload={handleImageUpload}
        onVideoUpload={handleVideoUpload}
      />
    </div>
  );
};

export default App;
