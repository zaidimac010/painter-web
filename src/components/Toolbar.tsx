import { motion, AnimatePresence } from 'framer-motion';
import {
  PencilIcon,
  BackspaceIcon,
  ArrowUturnLeftIcon,
  ArrowUturnRightIcon,
  TrashIcon,
  PhotoIcon,
  VideoCameraIcon,
} from '@heroicons/react/24/outline';
import { useState, useRef } from 'react';

interface ToolbarProps {
  onToolChange: (tool: 'pen' | 'eraser') => void;
  onColorChange: (color: string) => void;
  onSizeChange: (size: number) => void;
  onUndo: () => void;
  onRedo: () => void;
  onClear: () => void;
  onImageUpload: (file: File) => void;
  onVideoUpload: (file: File) => void;
  currentTool: 'pen' | 'eraser';
  currentColor: string;
  currentSize: number;
}

const colors = [
  { name: 'Black', value: '#000000' },
  { name: 'Red', value: '#FF0000' },
  { name: 'Blue', value: '#0000FF' },
  { name: 'Green', value: '#00FF00' },
];

const SizePopup = ({ 
  size, 
  onSizeChange, 
  tool,
  position 
}: { 
  size: number; 
  onSizeChange: (size: number) => void;
  tool: 'pen' | 'eraser';
  position: { x: number; y: number };
}) => (
  <motion.div
    initial={{ opacity: 0, scale: 0.9, y: 10 }}
    animate={{ opacity: 1, scale: 1, y: 0 }}
    exit={{ opacity: 0, scale: 0.9, y: 10 }}
    className="fixed bg-white/95 backdrop-blur-md rounded-2xl shadow-lg p-4 flex flex-col items-center gap-2"
    style={{ 
      left: position.x,
      bottom: position.y,
      transform: 'translate(-50%, 0)',
      width: '200px',
      zIndex: 50,
      willChange: 'transform'
    }}
  >
    <div className="text-sm font-medium text-gray-700">
      {tool === 'pen' ? 'Brush' : 'Eraser'} Size: {size}
    </div>
    <div className="w-full px-2">
      <input
        type="range"
        min="1"
        max="50"
        value={size}
        onChange={(e) => {
          const newSize = Number(e.target.value);
          requestAnimationFrame(() => onSizeChange(newSize));
        }}
        className="w-full h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-indigo-600 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:bg-indigo-600 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:transition-all hover:[&::-webkit-slider-thumb]:scale-110"
      />
    </div>
    <div className="w-full h-12 flex items-center justify-center">
      <motion.div 
        className="rounded-full bg-current transition-all"
        animate={{ 
          width: `${size}px`, 
          height: `${size}px` 
        }}
        style={{ 
          backgroundColor: tool === 'pen' ? 'black' : '#666'
        }} 
      />
    </div>
  </motion.div>
);

const Toolbar: React.FC<ToolbarProps> = ({
  onToolChange,
  onColorChange,
  onSizeChange,
  onUndo,
  onRedo,
  onClear,
  onImageUpload,
  onVideoUpload,
  currentTool,
  currentColor,
  currentSize,
}) => {
  const [showSizePopup, setShowSizePopup] = useState(false);
  const [popupPosition, setPopupPosition] = useState({ x: 0, y: 0 });
  const imageInputRef = useRef<HTMLInputElement>(null);
  const videoInputRef = useRef<HTMLInputElement>(null);

  const handleToolClick = (tool: 'pen' | 'eraser', event: React.MouseEvent) => {
    const button = event.currentTarget;
    const rect = button.getBoundingClientRect();
    const popupMargin = 16; // Space between popup and button
    
    setPopupPosition({ 
      x: Math.round(rect.left + (rect.width / 2)),
      y: Math.round(window.innerHeight - rect.top + popupMargin)
    });
    
    if (currentTool === tool) {
      setShowSizePopup(!showSizePopup);
    } else {
      onToolChange(tool);
      setShowSizePopup(true);
    }
  };

  const handleImageUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file && file.type.startsWith('image/')) {
      onImageUpload(file);
    }
    if (imageInputRef.current) {
      imageInputRef.current.value = '';
    }
  };

  const handleVideoUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file && file.type.startsWith('video/')) {
      onVideoUpload(file);
    }
    if (videoInputRef.current) {
      videoInputRef.current.value = '';
    }
  };

  return (
    <>
      <input
        type="file"
        ref={imageInputRef}
        onChange={handleImageUpload}
        accept="image/*"
        className="hidden"
      />
      <input
        type="file"
        ref={videoInputRef}
        onChange={handleVideoUpload}
        accept="video/*"
        className="hidden"
      />
      <motion.div
        className="fixed bottom-4 inset-x-0 flex justify-center items-center z-40"
        initial={{ y: 100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ type: 'spring', damping: 20, stiffness: 300 }}
      >
        <motion.div
          className="bg-white/90 backdrop-blur-md rounded-full px-5 py-3 flex items-center gap-3 mx-auto relative"
          whileHover={{ scale: 1.02 }}
          transition={{ type: 'spring', damping: 20, stiffness: 400 }}
          style={{
            boxShadow: '0 -10px 15px -3px rgba(0, 0, 0, 0.1), 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 -4px 6px -4px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1)',
          }}
        >
          {/* Drawing Tools */}
          <div className="flex items-center gap-2 border-r border-gray-200/50 pr-3">
            <motion.button
              whileHover={{ scale: 1.1, backgroundColor: '#EEF2FF' }}
              whileTap={{ scale: 0.95 }}
              onClick={(e) => handleToolClick('pen', e)}
              className={`p-2 rounded-full transition-colors ${
                currentTool === 'pen'
                  ? 'bg-indigo-100 text-indigo-600 ring-2 ring-indigo-400 ring-offset-2 ring-offset-white/90'
                  : 'hover:bg-gray-100 text-gray-600'
              }`}
            >
              <PencilIcon className="w-5 h-5" />
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.1, backgroundColor: '#EEF2FF' }}
              whileTap={{ scale: 0.95 }}
              onClick={(e) => handleToolClick('eraser', e)}
              className={`p-2 rounded-full transition-colors ${
                currentTool === 'eraser'
                  ? 'bg-indigo-100 text-indigo-600 ring-2 ring-indigo-400 ring-offset-2 ring-offset-white/90'
                  : 'hover:bg-gray-100 text-gray-600'
              }`}
            >
              <BackspaceIcon className="w-5 h-5" />
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.1, backgroundColor: '#EEF2FF' }}
              whileTap={{ scale: 0.95 }}
              onClick={() => imageInputRef.current?.click()}
              className="p-2 rounded-full hover:bg-gray-100 text-gray-600"
            >
              <PhotoIcon className="w-5 h-5" />
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.1, backgroundColor: '#EEF2FF' }}
              whileTap={{ scale: 0.95 }}
              onClick={() => videoInputRef.current?.click()}
              className="p-2 rounded-full hover:bg-gray-100 text-gray-600"
            >
              <VideoCameraIcon className="w-5 h-5" />
            </motion.button>
          </div>

          {/* Colors */}
          <div className="flex items-center gap-1.5 border-r border-gray-200/50 pr-3">
            <div className="flex gap-1.5">
              {colors.map((color) => (
                <button
                  key={color.value}
                  onClick={() => onColorChange(color.value)}
                  className={`w-6 h-6 rounded-full transition-colors relative ${
                    currentColor === color.value ? 'ring-2 ring-indigo-500 ring-offset-2 ring-offset-white/90' : ''
                  }`}
                  style={{ backgroundColor: color.value }}
                >
                  {currentColor === color.value && (
                    <div className="absolute inset-0 rounded-full ring-2 ring-white" />
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-1.5">
            <motion.button
              whileHover={{ scale: 1.1, backgroundColor: '#EEF2FF' }}
              whileTap={{ scale: 0.95 }}
              onClick={onUndo}
              className="p-2 rounded-full hover:bg-gray-100 text-gray-600"
            >
              <ArrowUturnLeftIcon className="w-5 h-5" />
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.1, backgroundColor: '#EEF2FF' }}
              whileTap={{ scale: 0.95 }}
              onClick={onRedo}
              className="p-2 rounded-full hover:bg-gray-100 text-gray-600"
            >
              <ArrowUturnRightIcon className="w-5 h-5" />
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.1, backgroundColor: '#FEE2E2' }}
              whileTap={{ scale: 0.95 }}
              onClick={onClear}
              className="p-2 rounded-full hover:bg-red-100 text-red-600"
            >
              <TrashIcon className="w-5 h-5" />
            </motion.button>
          </div>
        </motion.div>
      </motion.div>

      {/* Size Popup */}
      <AnimatePresence>
        {showSizePopup && (
          <div 
            className="fixed inset-0 z-30"
            onClick={() => setShowSizePopup(false)}
          >
            <div onClick={e => e.stopPropagation()}>
              <SizePopup
                size={currentSize}
                onSizeChange={onSizeChange}
                tool={currentTool}
                position={popupPosition}
              />
            </div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
};

export default Toolbar;
