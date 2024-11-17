import { useEffect, useRef } from 'react';
import type { WorkerMessage, WorkerResponse } from '../workers/canvasWorker';

// Import the worker using webpack worker-loader
const CanvasWorker = new Worker(new URL('../workers/canvasWorker.ts', import.meta.url), {
  type: 'module'
});

export function useCanvasWorker() {
  const workerRef = useRef<Worker | null>(null);

  useEffect(() => {
    // Use the pre-initialized worker
    workerRef.current = CanvasWorker;

    // Cleanup
    return () => {
      if (workerRef.current) {
        // Don't terminate the worker, just remove our reference
        workerRef.current = null;
      }
    };
  }, []);

  const processImageData = (
    imageData: ImageData,
    options?: WorkerMessage['options']
  ): Promise<ImageData> => {
    return new Promise((resolve, reject) => {
      if (!workerRef.current) {
        reject(new Error('Worker not initialized'));
        return;
      }

      const handleMessage = (e: MessageEvent<WorkerResponse>) => {
        workerRef.current?.removeEventListener('message', handleMessage);
        resolve(e.data.data);
      };

      const handleError = (error: ErrorEvent) => {
        workerRef.current?.removeEventListener('error', handleError);
        reject(error);
      };

      workerRef.current.addEventListener('message', handleMessage);
      workerRef.current.addEventListener('error', handleError);

      workerRef.current.postMessage({
        type: 'processImageData',
        data: imageData,
        options
      });
    });
  };

  const applyFilter = (
    imageData: ImageData,
    filter: string,
    intensity: number = 1
  ): Promise<ImageData> => {
    return new Promise((resolve, reject) => {
      if (!workerRef.current) {
        reject(new Error('Worker not initialized'));
        return;
      }

      const handleMessage = (e: MessageEvent<WorkerResponse>) => {
        workerRef.current?.removeEventListener('message', handleMessage);
        resolve(e.data.data);
      };

      const handleError = (error: ErrorEvent) => {
        workerRef.current?.removeEventListener('error', handleError);
        reject(error);
      };

      workerRef.current.addEventListener('message', handleMessage);
      workerRef.current.addEventListener('error', handleError);

      workerRef.current.postMessage({
        type: 'applyFilter',
        data: imageData,
        options: { filter, intensity }
      });
    });
  };

  return {
    processImageData,
    applyFilter
  };
}
