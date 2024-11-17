module.exports = {
  webpack: {
    configure: (webpackConfig) => {
      // Add worker-loader
      webpackConfig.module.rules.push({
        test: /\.worker\.(js|ts)$/,
        use: {
          loader: 'worker-loader',
          options: {
            filename: '[name].[contenthash].worker.js',
          },
        },
      });

      // Handle ESM modules properly
      webpackConfig.resolve.fallback = {
        ...webpackConfig.resolve.fallback,
        module: false,
      };

      // Ensure proper module resolution
      webpackConfig.resolve.extensionAlias = {
        '.js': ['.js', '.ts', '.tsx', '.jsx'],
        '.mjs': ['.mjs', '.mts'],
        '.cjs': ['.cjs', '.cts'],
      };

      return webpackConfig;
    },
  },
};
