// Performance monitoring utilities

export class PerformanceMonitor {
  private static instance: PerformanceMonitor;
  private metrics: Map<string, number[]>;
  private marks: Map<string, number>;

  private constructor() {
    this.metrics = new Map();
    this.marks = new Map();
  }

  static getInstance(): PerformanceMonitor {
    if (!PerformanceMonitor.instance) {
      PerformanceMonitor.instance = new PerformanceMonitor();
    }
    return PerformanceMonitor.instance;
  }

  // Start timing an operation
  mark(name: string): void {
    this.marks.set(name, performance.now());
  }

  // End timing and record the duration
  measure(name: string): number {
    const startTime = this.marks.get(name);
    if (!startTime) {
      console.warn(`No mark found for: ${name}`);
      return 0;
    }

    const duration = performance.now() - startTime;
    this.recordMetric(name, duration);
    this.marks.delete(name);
    return duration;
  }

  // Record a performance metric
  private recordMetric(name: string, value: number): void {
    const metrics = this.metrics.get(name) || [];
    metrics.push(value);
    // Keep only the last 100 measurements
    if (metrics.length > 100) {
      metrics.shift();
    }
    this.metrics.set(name, metrics);
  }

  // Get average performance for a metric
  getAverage(name: string): number {
    const metrics = this.metrics.get(name);
    if (!metrics || metrics.length === 0) return 0;

    const sum = metrics.reduce((acc, val) => acc + val, 0);
    return sum / metrics.length;
  }

  // Get performance percentile
  getPercentile(name: string, percentile: number): number {
    const metrics = this.metrics.get(name);
    if (!metrics || metrics.length === 0) return 0;

    const sorted = [...metrics].sort((a, b) => a - b);
    const index = Math.ceil((percentile / 100) * sorted.length) - 1;
    return sorted[index];
  }

  // Check if performance is degrading
  isPerformanceDegrading(name: string): boolean {
    const metrics = this.metrics.get(name);
    if (!metrics || metrics.length < 10) return false;

    const recentAvg = this.getAverageOfLastN(name, 5);
    const historicalAvg = this.getAverageOfLastN(name, metrics.length);

    return recentAvg > historicalAvg * 1.2; // 20% degradation threshold
  }

  private getAverageOfLastN(name: string, n: number): number {
    const metrics = this.metrics.get(name);
    if (!metrics || metrics.length === 0) return 0;

    const lastN = metrics.slice(-Math.min(n, metrics.length));
    const sum = lastN.reduce((acc, val) => acc + val, 0);
    return sum / lastN.length;
  }

  // Get performance report
  getReport(): Record<string, any> {
    const report: Record<string, any> = {};
    
    // Use Array.from instead of for...of with entries()
    Array.from(this.metrics.keys()).forEach(name => {
      const metrics = this.metrics.get(name)!;
      report[name] = {
        average: this.getAverage(name),
        p95: this.getPercentile(name, 95),
        p99: this.getPercentile(name, 99),
        isDegrading: this.isPerformanceDegrading(name),
        sampleSize: metrics.length
      };
    });

    return report;
  }

  // Clear all metrics
  clear(): void {
    this.metrics.clear();
    this.marks.clear();
  }
}
