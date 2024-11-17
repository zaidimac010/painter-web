/// <reference lib="webworker" />

export interface WorkerMessage {
  type: 'processImageData' | 'applyFilter';
  data: ImageData;
  options?: {
    filter?: string;
    intensity?: number;
  };
}

export interface WorkerResponse {
  type: 'processedImageData' | 'filteredImageData';
  data: ImageData;
}

// Declare the worker scope type
declare const self: DedicatedWorkerGlobalScope;

self.onmessage = (e: MessageEvent<WorkerMessage>) => {
  const { type, data, options } = e.data;

  switch (type) {
    case 'processImageData':
      // Process image data without blocking the main thread
      const processed = processImageData(data);
      self.postMessage({ type: 'processedImageData', data: processed });
      break;

    case 'applyFilter':
      // Apply filters in the background
      const filtered = applyFilter(data, options?.filter || '', options?.intensity || 1);
      self.postMessage({ type: 'filteredImageData', data: filtered });
      break;
  }
};

function processImageData(imageData: ImageData): ImageData {
  // Clone the image data to avoid modifying the original
  const processed = new ImageData(
    new Uint8ClampedArray(imageData.data),
    imageData.width,
    imageData.height
  );

  // Optimize pixel manipulation
  const data = processed.data;
  for (let i = 0; i < data.length; i += 4) {
    // Implement any heavy pixel processing here
    // This runs in a separate thread, so it won't block the UI
  }

  return processed;
}

function applyFilter(imageData: ImageData, filter: string, intensity: number): ImageData {
  const filtered = new ImageData(
    new Uint8ClampedArray(imageData.data),
    imageData.width,
    imageData.height
  );

  const data = filtered.data;
  switch (filter) {
    case 'blur':
      // Implement blur filter
      break;
    case 'sharpen':
      // Implement sharpen filter
      break;
    case 'brighten':
      for (let i = 0; i < data.length; i += 4) {
        data[i] = Math.min(255, data[i] + intensity * 255);     // Red
        data[i + 1] = Math.min(255, data[i + 1] + intensity * 255); // Green
        data[i + 2] = Math.min(255, data[i + 2] + intensity * 255); // Blue
      }
      break;
  }

  return filtered;
}

// Export empty object to make it a module
export {};
